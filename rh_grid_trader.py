import uuid
import requests
import base64
import datetime
import logging
import os
import time
import argparse
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from decimal import Decimal, ROUND_DOWN

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

API_KEY = os.getenv('RH_API_KEY')
BASE64_PRIVATE_KEY = os.getenv('RH_BASE64_PRIVATE_KEY')

class GridTrader:
    def __init__(self, grid_size, usd_position_size, poll_interval=60):
        self.grid_size = grid_size
        self.usd_position_size = usd_position_size
        self.api_key = API_KEY
        self.private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(BASE64_PRIVATE_KEY))
        self.base_url = "https://trading.robinhood.com"
        self.open_orders = []  # In-memory structure to track open orders
        self.poll_interval = poll_interval  # Interval to check for price updates
        logging.info(f"Initialized GridTrader: {grid_size=}, {usd_position_size=}")

    def round_to_decimal_places(self, value: float, places: int) -> float:
        """Round the value to a specific number of decimal places."""
        return float(Decimal(value).quantize(Decimal(10) ** -places, rounding=ROUND_DOWN))

    def round_asset_quantity(self, quantity: float) -> float:
        """Round asset quantity to 8 decimal places."""
        return float(Decimal(quantity).quantize(Decimal('1.00000000'), rounding=ROUND_DOWN))

    def place_order(self, side: str, price: float, quantity: float = None) -> dict:
        client_order_id = str(uuid.uuid4())
        body = {
            "client_order_id": client_order_id,
            "side": side,
            "type": "limit",
            "symbol": "BTC-USD",
            "limit_order_config": {
                "limit_price": str(self.round_to_decimal_places(price, 2)),
                "time_in_force": "gtc"
            }
        }

        if side == "buy":
            body["limit_order_config"]["quote_amount"] = str(self.round_to_decimal_places(self.usd_position_size, 2))
        elif side == "sell":
            body["limit_order_config"]["asset_quantity"] = str(self.round_asset_quantity(quantity))

        path = "/api/v1/crypto/trading/orders/"
        headers = self.get_authorization_header("POST", path, json.dumps(body), self._get_current_timestamp())
        url = self.base_url + path
        logging.info(f"Placing {side} order at ${price} with body: {body}")
        try:
            response = requests.post(url, headers=headers, json=body, timeout=10)
            response.raise_for_status()
            order_response = response.json()
            logging.info(f"Order Response: {order_response}")
            self.open_orders.append(order_response)
            return order_response
        except requests.RequestException as e:
            logging.error(f"Error placing order: {e}")
            return {}

    def _get_current_timestamp(self) -> int:
        return int(datetime.datetime.now(datetime.timezone.utc).timestamp())

    def get_authorization_header(self, method: str, path: str, body: str, timestamp: int) -> dict:
        message_to_sign = f"{self.api_key}{timestamp}{path}{method}{body}"
        signature = self.private_key.sign(message_to_sign.encode("utf-8"))
        return {
            "x-api-key": self.api_key,
            "x-signature": base64.b64encode(signature).decode("utf-8"),
            "x-timestamp": str(timestamp),
        }

    def get_best_bid_ask(self, symbol: str) -> dict:
        path = f"/api/v1/crypto/marketdata/best_bid_ask/?symbol={symbol}"
        headers = self.get_authorization_header("GET", path, "", self._get_current_timestamp())
        url = self.base_url + path
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Error fetching best bid/ask: {e}")
            return {}

    def get_current_price(self) -> float:
        best_bid_ask = self.get_best_bid_ask("BTC-USD")
        if 'results' in best_bid_ask and best_bid_ask['results']:
            try:
                current_price = float(best_bid_ask['results'][0]['ask_inclusive_of_buy_spread'])
                logging.info(f"BTC price: ${current_price}")
                return current_price
            except (KeyError, ValueError) as e:
                logging.error(f"Error parsing price: {e}")
                return None
        else:
            logging.error(f"'ask_inclusive_of_buy_spread' not found in response: {best_bid_ask}")
            return None

    def update_order_statuses(self):
        """Fetches and updates the status of open orders."""
        for order in self.open_orders:
            order_id = order['id']
            status = self.get_order_status(order_id)
            if status['state'] == 'filled':
                self.open_orders.remove(order)
                logging.info(f"Order {order_id} has been filled and removed from tracking.")
            else:
                logging.info(f"Order {order_id} status: {status['state']}")

    def get_order_status(self, order_id: str) -> dict:
        path = f"/api/v1/crypto/trading/orders/{order_id}/"
        headers = self.get_authorization_header("GET", path, "", self._get_current_timestamp())
        url = self.base_url + path
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Error fetching order status: {e}")
            return {}

    def dynamic_grid_trading_strategy(self):
        current_price = self.get_current_price()
        if current_price is None:
            return

        lower_bound = current_price - 1500

        # Place buys below the current price
        for price in range(int(lower_bound), int(current_price), int(self.grid_size)):
            buy_order = self.place_order("buy", price)
            if buy_order:
                quantity_bought = self.usd_position_size / price
                logging.info(f"Placed buy order at ${price} for {quantity_bought} BTC.")

        # Update and place corresponding sells for filled buys
        self.update_order_statuses()
        for order in self.open_orders:
            if order['side'] == 'buy' and order['state'] == 'filled':
                buy_price = float(order['limit_order_config']['limit_price'])
                sell_price = buy_price + 2 * (current_price - buy_price)
                self.place_order("sell", sell_price, float(order['limit_order_config']['asset_quantity']))

    def run(self):
        logging.info("Running Grid Trading Strategy")
        while True:
            self.dynamic_grid_trading_strategy()
            time.sleep(self.poll_interval)  # Wait before checking prices and placing orders again

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Grid Trading Bot')
    parser.add_argument('--grid-size', type=float, required=True, help='Grid size in USD')
    parser.add_argument('--usd-position-size', type=float, required=True, help='USD position size per trade')
    parser.add_argument('--poll-interval', type=int, default=60, help='Time interval (in seconds) between strategy runs')

    args = parser.parse_args()

    trader = GridTrader(
        grid_size=args.grid_size,
        usd_position_size=args.usd_position_size,
        poll_interval=args.poll_interval
    )
    trader.run()
