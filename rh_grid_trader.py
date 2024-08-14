import uuid
import json
import requests
import base64
import datetime
import logging
import argparse
import os
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
    def __init__(self, grid_size, usd_position_size):
        self.grid_size = grid_size
        self.usd_position_size = usd_position_size
        self.api_key = API_KEY
        self.private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(BASE64_PRIVATE_KEY))
        self.base_url = "https://trading.robinhood.com"
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
                "limit_price": str(self.round_to_decimal_places(price, 2)),  # Round price to 2 decimal places
                "time_in_force": "gtc"
            }
        }

        if side == "buy":
            body["limit_order_config"]["quote_amount"] = str(self.round_to_decimal_places(self.usd_position_size, 2))
        elif side == "sell":
            # Ensure quantity is rounded to 8 decimal places
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
            return order_response
        except requests.RequestException as e:
            logging.error(f"Error placing order: {e}")
            if response is not None:
                logging.error(f"Response content: {response.text}")
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

    def log_filled_order(self, action: str, price: float, quantity: float, order_id: str):
        log_entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "price": price,
            "quantity": quantity,
            "order_id": order_id
        }

        log_file = 'buy_placed.json' if action == "buy" else 'sell_placed.json'

        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
        
        logging.info(f"Logged filled order: {log_entry}")

    def load_filled_orders(self, action: str):
        """Load filled orders from the respective JSON file."""
        file_name = 'buy_placed.json' if action == "buy" else 'sell_placed.json'
        try:
            with open(file_name, 'r') as f:
                return [json.loads(line) for line in f]
        except FileNotFoundError:
            return []

    def grid_trading_strategy(self):
        current_price = self.get_current_price()
        if current_price is None:
            return

        lower_bound = current_price - 1500
        upper_bound = current_price + 1500

        # Place buys below the current price and track them
        for price in range(int(lower_bound), int(current_price), int(self.grid_size)):
            buy_order = self.place_order("buy", price)
            if buy_order:
                quantity_bought = self.usd_position_size / price
                self.log_filled_order("buy", price, self.round_asset_quantity(quantity_bought), buy_order['id'])

        # Place corresponding sells based on previously filled buys
        filled_buys = self.load_filled_orders("buy")
        for buy in filled_buys:
            buy_price = buy['price']
            buy_quantity = buy['quantity']
            sell_price = buy_price + 2 * (current_price - buy_price)  # Reflective scaling
            sell_order = self.place_order("sell", sell_price, buy_quantity)
            if sell_order:
                self.log_filled_order("sell", sell_price, buy_quantity, sell_order['id'])

    def run(self):
        logging.info("Running Grid Trading Strategy")
        self.grid_trading_strategy()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Grid Trading Bot')
    parser.add_argument('--grid-size', type=float, required=True, help='Grid size in USD')
    parser.add_argument('--usd-position-size', type=float, required=True, help='USD position size per trade')

    args = parser.parse_args()

    trader = GridTrader(
        grid_size=args.grid_size,
        usd_position_size=args.usd_position_size
    )
    trader.run()
