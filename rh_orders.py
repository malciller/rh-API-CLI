import requests
import base64
import datetime
import logging
import os
import argparse
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

API_KEY = os.getenv('RH_API_KEY')
BASE64_PRIVATE_KEY = os.getenv('RH_BASE64_PRIVATE_KEY')

class CryptoOrderFetcher:
    def __init__(self):
        self.api_key = API_KEY
        private_key_bytes = base64.b64decode(BASE64_PRIVATE_KEY)
        
        if len(private_key_bytes) != 32:
            raise ValueError("Private key must be 32 bytes long")
        
        self.private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
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
        path = "/api/v1/crypto/trading/orders/"
        headers = self.get_authorization_header("GET", path, "", self._get_current_timestamp())
        url = self.base_url + path

        all_orders = []
        while url:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 401:
                    logging.error(f"Unauthorized request. Response content: {response.text}")
                    break

                response.raise_for_status()
                data = response.json()
                orders = data.get('results', [])
                if not orders:
                    logging.info("No more orders found.")
                    break

                all_orders.extend(orders)
                url = data.get('next')  # Handle pagination
            except requests.exceptions.HTTPError as http_err:
                logging.error(f"HTTP error occurred: {http_err}")
                break
            except requests.exceptions.RequestException as req_err:
                logging.error(f"Request error occurred: {req_err}")
                break
            except ValueError as json_err:
                logging.error(f"JSON decoding error: {json_err}")
                break

        return all_orders

    def filter_orders(self, orders: list, order_type: str, status: str) -> list:
        filtered_orders = []
        for order in orders:
            if order['side'] == order_type and order['state'] == status:
                filtered_orders.append(order)
        return filtered_orders

    def print_orders(self, orders: list):
        counts = self.count_orders(orders)

        for order in orders:
            if order['state'] != 'canceled':
                limit_price = order.get('limit_order_config', {}).get('limit_price', 'N/A')
                
                if order.get('side') == 'buy':
                    # For buy orders, get the quote_amount
                    asset_value = order.get('limit_order_config', {}).get('quote_amount', 'N/A')
                elif order.get('side') == 'sell':
                    # For sell orders, get the asset_quantity
                    asset_value = order.get('limit_order_config', {}).get('asset_quantity', 'N/A')
                
                print(f"Order ID: {order.get('id')}")
                print(f"Symbol: {order.get('symbol')}")
                print(f"Side: {order.get('side')}")
                print(f"Type: {order.get('type')}")
                print(f"State: {order.get('state')}")
                print(f"Created At: {order.get('created_at')}")
                print(f"Updated At: {order.get('updated_at')}")
                print(f"Asset Value: {asset_value}")  # Print the asset value (either quote_amount or asset_quantity)
                print(f"Limit Price: ${limit_price}")
                print('-' * 40)



        print(f"Total Open Buy Orders: {counts['open_buy']}")
        print(f"Total Open Sell Orders: {counts['open_sell']}")
        print(f"Total Filled Buy Orders: {counts['filled_buy']}")
        print(f"Total Filled Sell Orders: {counts['filled_sell']}")

    def count_orders(self, orders: list) -> dict:
        """Count total open and filled buy and sell orders."""
        counts = {'open_buy': 0, 'open_sell': 0, 'filled_buy': 0, 'filled_sell': 0}
        for order in orders:
            if order['state'] == 'filled':
                if order['side'] == 'buy':
                    counts['filled_buy'] += 1
                else:
                    counts['filled_sell'] += 1
            elif order['state'] != 'canceled':
                if order['side'] == 'buy':
                    counts['open_buy'] += 1
                else:
                    counts['open_sell'] += 1

        return counts

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch and filter crypto orders.")
    parser.add_argument("--type", choices=["buy", "sell"], required=True, help="Type of the order (buy or sell).")
    parser.add_argument("--status", choices=["filled", "open"], required=True, help="Status of the order (filled or open).")

    args = parser.parse_args()

    fetcher = CryptoOrderFetcher()
    all_orders = fetcher.get_all_orders()
    filtered_orders = fetcher.filter_orders(all_orders, args.type, args.status)
    fetcher.print_orders(filtered_orders)
