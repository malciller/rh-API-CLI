import uuid
import json
import requests
import base64
import datetime
import logging
import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

API_KEY = os.getenv('RH_API_KEY')
BASE64_PRIVATE_KEY = os.getenv('RH_BASE64_PRIVATE_KEY')

class OrderCanceller:
    def __init__(self):
        self.api_key = API_KEY
        self.private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(BASE64_PRIVATE_KEY))
        self.base_url = "https://trading.robinhood.com"

    def _get_current_timestamp(self) -> int:
        return int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())

    def get_authorization_header(self, method: str, path: str, body: str, timestamp: int) -> dict:
        message_to_sign = f"{self.api_key}{timestamp}{path}{method}{body}"
        signature = self.private_key.sign(message_to_sign.encode("utf-8"))
        return {
            "x-api-key": self.api_key,
            "x-signature": base64.b64encode(signature).decode("utf-8"),
            "x-timestamp": str(timestamp),
        }

    def get_all_orders(self) -> list:
        """Fetch all orders (open and filled), handling pagination."""
        path = "/api/v1/crypto/trading/orders/"
        headers = self.get_authorization_header("GET", path, "", self._get_current_timestamp())
        url = self.base_url + path

        all_orders = []
        while url:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()  # Raise an exception for HTTP errors
                data = response.json()
            except requests.exceptions.HTTPError as http_err:
                logging.error(f"HTTP error occurred: {http_err}")
                break
            except requests.exceptions.RequestException as req_err:
                logging.error(f"Request error occurred: {req_err}")
                break
            except ValueError as json_err:
                logging.error(f"JSON decoding error: {json_err}")
                break

            orders = data.get('results', [])
            if not orders:
                logging.info("No more orders found.")
                break

            all_orders.extend(orders)
            url = data.get('next')  # Handle pagination

        return all_orders

    def get_order_status(self, order_id: str) -> dict:
        """Retrieve the current status of an order by its ID."""
        path = f"/api/v1/crypto/trading/orders/{order_id}/"
        headers = self.get_authorization_header("GET", path, "", self._get_current_timestamp())
        url = self.base_url + path
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP error occurred: {http_err}")
        except requests.exceptions.RequestException as req_err:
            logging.error(f"Request error occurred: {req_err}")
        except ValueError as json_err:
            logging.error(f"JSON decoding error: {json_err}")

        return {}

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a specific order by its ID."""
        path = f"/api/v1/crypto/trading/orders/{order_id}/cancel/"
        headers = self.get_authorization_header("POST", path, "", self._get_current_timestamp())
        url = self.base_url + path
        try:
            response = requests.post(url, headers=headers, timeout=10)
            response.raise_for_status()

            # Check if the response is plain text
            if response.headers.get("Content-Type") == "text/plain":
                return {"success": response.text.strip()}
            else:
                logging.error(f"Unexpected content type: {response.headers.get('Content-Type')}")
                return {"error": response.text}
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP error occurred: {http_err}")
        except requests.exceptions.RequestException as req_err:
            logging.error(f"Request error occurred: {req_err}")
        except ValueError as json_err:
            logging.error(f"JSON decoding error: {json_err}")

        return {}


    def cancel_all_orders(self):
        """Cancel all orders."""
        all_orders = self.get_all_orders()
        for order in all_orders:
            order_id = order.get('id')
            if not order_id:
                logging.warning("Order ID not found.")
                continue

            current_status = self.get_order_status(order_id)
            if not current_status:
                logging.warning(f"Could not retrieve status for order {order_id}.")
                continue

            status = current_status.get('state')
            logging.info(f"Order {order_id} status: {status}")

            if status == 'open':
                logging.info(f"Cancelling order {order_id}...")
                cancel_response = self.cancel_order(order_id)
                if 'error' in cancel_response:
                    logging.error(f"Cannot cancel order {order_id}: {cancel_response.get('error')}")
                elif 'success' in cancel_response:
                    logging.info(f"Order {order_id} successfully canceled. Response: {cancel_response.get('success')}")
                else:
                    logging.error(f"Unexpected response for order {order_id}: {cancel_response}")
            else:
                logging.info(f"Skipping cancellation for order {order_id} - current status: {status}")

if __name__ == "__main__":
    canceller = OrderCanceller()
    canceller.cancel_all_orders()
