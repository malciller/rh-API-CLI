import json
import logging
from rh_orders import CryptoOrderFetcher
from rh_grid_trader import GridTrader  # Import the GridTrader class

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

BUY_PLACED_FILE = "buy_placed.json"
SELL_PLACED_FILE = "sell_placed.json"
BUY_FILLED_FILE = "buy_filled.json"
SELL_FILLED_FILE = "sell_filled.json"

class ProfitCalculator:
    def __init__(self, buy_placed_file, sell_placed_file, buy_filled_file, sell_filled_file, grid_trader):
        self.buy_placed_file = buy_placed_file
        self.sell_placed_file = sell_placed_file
        self.buy_filled_file = buy_filled_file
        self.sell_filled_file = sell_filled_file
        self.fetcher = CryptoOrderFetcher()  # Initialize CryptoOrderFetcher
        self.grid_trader = grid_trader  # Instance of GridTrader for real-time price

    def _read_json_file(self, file_path):
        """Reads data from a JSON file."""
        try:
            with open(file_path, 'r') as file:
                data = [json.loads(line) for line in file]
            return data
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.error(f"Error reading file {file_path}: {e}")
            return []

    def _write_json_file(self, file_path, data):
        """Writes data to a JSON file."""
        try:
            with open(file_path, 'a') as file:
                file.write(json.dumps(data) + "\n")
        except IOError as e:
            logging.error(f"Error writing file {file_path}: {e}")
  
    def _update_filled_orders(self):
        """Updates filled orders from buy_placed and sell_placed files to buy_filled and sell_filled."""
        buy_placed = self._read_json_file(self.buy_placed_file)
        sell_placed = self._read_json_file(self.sell_placed_file)
        buy_filled = self._read_json_file(self.buy_filled_file)
        sell_filled = self._read_json_file(self.sell_filled_file)

        buy_filled_ids = {order['order_id'] for order in buy_filled}
        sell_filled_ids = {order['order_id'] for order in sell_filled}

        all_orders = self.fetcher.get_all_orders()  # Fetch all orders using CryptoOrderFetcher

        # Filter filled orders
        filled_orders = [order for order in all_orders if order['state'] == 'filled']

        # Update buy_filled and sell_filled files
        for order in filled_orders:
            price = float(order.get('limit_order_config', {}).get('limit_price', '0'))
            quote_amount = float(order.get('limit_order_config', {}).get('quote_amount', '0'))
            if price == 0:
                logging.warning(f"Order {order['id']} has a price of 0. Skipping.")
                continue

            quantity = 1.0 / price  # Assuming $1 investment per buy order

            if order['side'] == 'buy' and order['id'] not in buy_filled_ids:
                self._write_json_file(self.buy_filled_file, {
                    'timestamp': order.get('created_at'),
                    'price': price,
                    'quote_amount': quote_amount,
                    'quantity': quantity,
                    'order_id': order.get('id')
                })
            elif order['side'] == 'sell' and order['id'] not in sell_filled_ids:
                self._write_json_file(self.sell_filled_file, {
                    'timestamp': order.get('created_at'),
                    'price': price,
                    'quote_amount': quote_amount,
                    'quantity': quantity,
                    'order_id': order.get('id')
                })




    def _calculate_unrealized_gains(self, buys, sells, current_price):
        """Calculates unrealized gains based on current price."""
        unrealized_gains = 0.0

        # Create a list of open buy orders
        open_buys = [(buy['price'], buy['quantity']) for buy in buys]

        # Calculate unrealized gains
        for sell in sells:
            sell_price = sell['price']
            sell_quantity = sell['quantity']     
            remaining_quantity = sell_quantity

            # Match sell orders with open buy orders
            for i, (buy_price, buy_quantity) in enumerate(open_buys):
                if remaining_quantity <= 0:
                    break

                if buy_quantity > 0:
                    if buy_quantity <= remaining_quantity:
                        unrealized_gains += (sell_price - buy_price) * buy_quantity
                        remaining_quantity -= buy_quantity
                        open_buys[i] = (buy_price, 0)  # Mark this buy order as fully used
                    else:
                        unrealized_gains += (sell_price - buy_price) * remaining_quantity
                        open_buys[i] = (buy_price, buy_quantity - remaining_quantity)
                        remaining_quantity = 0

        # Handle any remaining open buys for unrealized gains
        for buy_price, buy_quantity in open_buys:
            unrealized_gains += (current_price - buy_price) * buy_quantity

        return unrealized_gains

    def _calculate_realized_gains(self, buys, sells):
        """Calculates realized gains based on filled orders."""
        realized_gains = 0.0

        # Process buy_filled.json data
        for buy in buys:
            realized_gains -= 1  # Subtract $1 for each buy order

        # Process sell_filled.json data
        for sell in sells:
            realized_gains += float(sell['price'])  # Add the sale price for each sell order

        return realized_gains




    def display_unrealized_gains(self):
        """Displays unrealized gains based on current price."""
        buys = self._read_json_file(self.buy_placed_file)
        sells = self._read_json_file(self.sell_placed_file)

        if not buys and not sells:
            logging.info("No buy or sell data found.")
            return

        current_price = self.grid_trader.get_current_price()
        if current_price is None:
            logging.error("Failed to retrieve current price.")
            return

        unrealized_gains = self._calculate_unrealized_gains(buys, sells, current_price)
        logging.info(f"Unrealized Gains: ${unrealized_gains:.2f}")

    def display_realized_gains(self):
        """Displays realized gains based on filled orders."""
        buys = self._read_json_file(self.buy_filled_file) or []
        sells = self._read_json_file(self.sell_filled_file) or []

        realized_gains = self._calculate_realized_gains(buys, sells)
        logging.info(f"Realized Gains: ${realized_gains:.2f}")



if __name__ == "__main__":
    grid_trader = GridTrader(grid_size=100, usd_position_size=5)  # Example initialization
    calculator = ProfitCalculator(
        buy_placed_file=BUY_PLACED_FILE,
        sell_placed_file=SELL_PLACED_FILE,
        buy_filled_file=BUY_FILLED_FILE,
        sell_filled_file=SELL_FILLED_FILE,
        grid_trader=grid_trader
    )

    calculator._update_filled_orders()
    calculator.display_unrealized_gains()
    calculator.display_realized_gains()
