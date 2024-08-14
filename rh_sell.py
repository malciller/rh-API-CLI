import argparse
import logging
from rh_grid_trader import GridTrader  # Import your GridTrader class from your grid trading script

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

class SellOrderPlacer:
    def __init__(self, initial_price, increment, total_orders, sell_amount):
        self.initial_price = initial_price
        self.increment = increment
        self.total_orders = total_orders
        self.sell_amount = sell_amount
        self.grid_trader = GridTrader(grid_size=increment, usd_position_size=sell_amount)
        logging.info(f"Initialized SellOrderPlacer: {initial_price=}, {increment=}, {total_orders=}, {sell_amount=}")

    def place_sell_orders(self):
        current_price = self.initial_price
        for i in range(self.total_orders):
            quantity = self.grid_trader.round_asset_quantity(self.sell_amount / current_price)
            sell_order = self.grid_trader.place_order("sell", current_price, quantity)
            if sell_order:
                self.grid_trader.log_filled_order("sell", current_price, quantity, sell_order['id'])
            current_price += self.increment  # Increment the price for the next order

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Place Limit Sell Orders for BTC')
    parser.add_argument('--initial-price', type=float, required=True, help='Initial price for the first sell order')
    parser.add_argument('--increment', type=float, required=True, help='Price increment between consecutive sell orders')
    parser.add_argument('--total-orders', type=int, required=True, help='Total number of sell orders to place')
    parser.add_argument('--sell-amount', type=float, required=True, help='Dollar amount for each sell order')

    args = parser.parse_args()

    sell_order_placer = SellOrderPlacer(
        initial_price=args.initial_price,
        increment=args.increment,
        total_orders=args.total_orders,
        sell_amount=args.sell_amount
    )

    sell_order_placer.place_sell_orders()
