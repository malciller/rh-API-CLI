import base64
import datetime
import json
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typing import Any, Dict, Optional
import uuid
import argparse
import os

API_KEY = os.getenv('RH_API_KEY')
BASE64_PRIVATE_KEY = os.getenv('RH_BASE64_PRIVATE_KEY')

class CryptoAPITrading:
    def __init__(self):
        self.api_key = API_KEY
        private_bytes = base64.b64decode(BASE64_PRIVATE_KEY)
        self.private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
        self.base_url = "https://trading.robinhood.com"

    @staticmethod
    def _get_current_timestamp() -> int:
        return int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())

    @staticmethod
    def get_query_params(key: str, *args: Optional[str]) -> str:
        if not args:
            return ""

        params = []
        for arg in args:
            params.append(f"{key}={arg}")

        return "?" + "&".join(params)

    def make_api_request(self, method: str, path: str, body: str = "") -> Any:
        timestamp = self._get_current_timestamp()
        headers = self.get_authorization_header(method, path, body, timestamp)
        url = self.base_url + path

        try:
            response = None
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=json.loads(body), timeout=10)
            return response.json()
        except requests.RequestException as e:
            print(f"Error making API request: {e}")
            return None

    def get_authorization_header(
            self, method: str, path: str, body: str, timestamp: int
    ) -> Dict[str, str]:
        message_to_sign = f"{self.api_key}{timestamp}{path}{method}{body}"
        signature = self.private_key.sign(message_to_sign.encode("utf-8"))

        return {
            "x-api-key": self.api_key,
            "x-signature": base64.b64encode(signature).decode("utf-8"),
            "x-timestamp": str(timestamp),
        }

    def get_account(self) -> Any:
        path = "/api/v1/crypto/trading/accounts/"
        return self.make_api_request("GET", path)

    def get_trading_pairs(self, *symbols: Optional[str]) -> Any:
        query_params = self.get_query_params("symbol", *symbols)
        path = f"/api/v1/crypto/trading/trading_pairs/{query_params}"
        return self.make_api_request("GET", path)

    def get_holdings(self, *asset_codes: Optional[str]) -> Any:
        query_params = self.get_query_params("asset_code", *asset_codes)
        path = f"/api/v1/crypto/trading/holdings/{query_params}"
        return self.make_api_request("GET", path)

    def get_best_bid_ask(self, *symbols: Optional[str]) -> Any:
        query_params = self.get_query_params("symbol", *symbols)
        path = f"/api/v1/crypto/marketdata/best_bid_ask/{query_params}"
        return self.make_api_request("GET", path)

    def get_estimated_price(self, symbol: str, side: str, quantity: str) -> Any:
        path = f"/api/v1/crypto/marketdata/estimated_price/?symbol={symbol}&side={side}&quantity={quantity}"
        return self.make_api_request("GET", path)

    def place_order(
            self,
            client_order_id: str,
            side: str,
            order_type: str,
            symbol: str,
            order_config: Dict[str, str],
    ) -> Any:
        body = {
            "client_order_id": client_order_id,
            "side": side,
            "type": order_type,
            "symbol": symbol,
            f"{order_type}_order_config": order_config,
        }
        path = "/api/v1/crypto/trading/orders/"
        return self.make_api_request("POST", path, json.dumps(body))

    def cancel_order(self, order_id: str) -> Any:
        path = f"/api/v1/crypto/trading/orders/{order_id}/cancel/"
        return self.make_api_request("POST", path)

    def get_order(self, order_id: str) -> Any:
        path = f"/api/v1/crypto/trading/orders/{order_id}/"
        return self.make_api_request("GET", path)

    def get_orders(self) -> Any:
        path = "/api/v1/crypto/trading/orders/"
        return self.make_api_request("GET", path)

    def get_current_btc_price(self) -> float:
        """Get the current Bitcoin price."""
        best_bid_ask = self.get_best_bid_ask("BTC-USD")
        print("Best Bid/Ask Response:", best_bid_ask)  # Debugging line
        
        # Check if the correct price field exists
        if 'results' in best_bid_ask and best_bid_ask['results']:
            return float(best_bid_ask['results'][0]['ask_inclusive_of_buy_spread'])
        else:
            raise KeyError(f"'ask_inclusive_of_buy_spread' not found in response: {best_bid_ask}")

    def execute_btc_daily_buy(self):
        """Execute the daily buy strategy for BTC."""
        current_price = self.get_current_btc_price()

        if current_price < 60500:
            # Buy $5 worth of Bitcoin
            buy_amount = 5
        else:
            # Buy $1 worth of Bitcoin
            buy_amount = 1

        # Calculate the asset quantity and round to 8 decimal places
        asset_quantity = round(buy_amount / current_price, 8)

        order = self.place_order(
            str(uuid.uuid4()),
            "buy",
            "market",
            "BTC-USD",
            {"asset_quantity": str(asset_quantity)}
        )
        print(f"Bought ${buy_amount} worth of Bitcoin at ${current_price}.")
        print("Order Response:", order)



def main():
    parser = argparse.ArgumentParser(description="Interact with the Robinhood Crypto API")
    parser.add_argument("action", choices=["get_account", "get_trading_pairs", "get_best_bid_ask", "place_order", "execute_btc_daily_buy"], help="The action to perform")
    parser.add_argument("--symbol", help="The symbol for trading pairs or best bid/ask")
    parser.add_argument("--quantity", help="The quantity for placing an order")
    
    args = parser.parse_args()

    api_trading_client = CryptoAPITrading()

    if args.action == "get_account":
        account_info = api_trading_client.get_account()
        print("Account Info:", account_info)
    elif args.action == "get_trading_pairs":
        symbols = args.symbol.split(",") if args.symbol else []
        trading_pairs = api_trading_client.get_trading_pairs(*symbols)
        print("Trading Pairs:", trading_pairs)
    elif args.action == "get_best_bid_ask":
        if not args.symbol:
            print("Symbol is required for get_best_bid_ask")
            return
        best_bid_ask = api_trading_client.get_best_bid_ask(args.symbol)
        print("Best Bid/Ask:", best_bid_ask)
    elif args.action == "place_order":
        if not args.symbol or not args.quantity:
            print("Symbol and quantity are required for place_order")
            return
        order = api_trading_client.place_order(
            str(uuid.uuid4()),
            "buy",
            "market",
            args.symbol,
            {"asset_quantity": args.quantity}
        )
        print("Order Response:", order)
    elif args.action == "execute_btc_daily_buy":
        api_trading_client.execute_btc_daily_buy()

if __name__ == "__main__":
    main()
