import os
import sys
import logging
import json
from datetime import datetime
from typing import Dict, Optional
from decimal import Decimal, ROUND_DOWN
import argparse

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
except ImportError:
    print("error: Binance API library is not installed. Please install it using 'pip install python-binance'.")
    sys.exit(1)
    
    
try:
    from config import BINANCE_API_KEY, BINANCE_API_SECRET, DEFAULT_TESTNET, MAX_ORDER_VALUE_USDT, MIN_ORDER_QUANTITY, REQUEST_DELAY
    CONFIG_AVAILABLE = True
    print("Configuration loaded successfully.")
except ImportError:
    CONFIG_AVAILABLE = False
    print("error: Configuration file not found. Please create a config.py file with your Binance API credentials and settings.")
    

class TradingBotLogger:
    
    def __init__(self, log_level=logging.INFO):
        self.logger = logging.getLogger('TradingBot')
        self.logger.setLevel(log_level)
        
        # cerate a log file if not there
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        file_handler = logging.FileHandler(f'logs/trading_bot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')  #file handler that creates a log file with timestamp
        file_handler.setLevel(logging.DEBUG)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        fromatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(fromatter)
        console_handler.setFormatter(fromatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    #functions to log requests, responses, errors, and order placements  
    def log_api_request(self, method: str, params: Dict):
        self.logger.info(f"API REQUEST - {method}: {json.dumps(params, indent=2)}")
    
    def log_api_response(self, method: str, response: Dict):
        self.logger.info(f"API RESPONSE - {method}: {json.dumps(response, indent=2)}")
    
    def log_error(self, error: Exception, context: str = ""):
        self.logger.error(f"ERROR {context}: {str(error)}")
    
    def log_order_placement(self, order_details: Dict):
        self.logger.info(f"ORDER PLACED: {json.dumps(order_details, indent=2)}")
        
        
class OrderValidator:
    
    @staticmethod
    def validate_symbol(symbol: str) -> str:
        symbol = symbol.upper().strip()
        if not symbol.endswith('USDT'):
            symbol += 'USDT'
        return symbol
    
    @staticmethod
    def validate_side(side: str) -> str:
        side = side.upper().strip()
        if side not in ['BUY', 'SELL']:
            raise ValueError(f"Invalid side: {side}. Must be 'BUY' or 'SELL'")
        return side
    
    @staticmethod
    def validate_quantity(quantity: float) -> float:
        if quantity <= 0:
            raise ValueError(f"Invalid quantity: {quantity}. Must be positive")
        return quantity
    
    @staticmethod
    def validate_price(price: float) -> float:
        if price <= 0:
            raise ValueError(f"Invalid price: {price}. Must be positive")
        return price
    
class BasicBot:
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = DEFAULT_TESTNET):
        
        self.api_key= api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        self.logger = TradingBotLogger()
        
        try:
            self.client = Client(
                api_key=api_key,
                api_secret=api_secret,
                testnet=testnet
            )
            self.client.ping()
            self.logger.logger.info("successfully connected to Binance API.")
            
            account_info = self.client.futures_account()
            self.logger.logger.info(f"Account balance: {account_info['totalWalletBalance']} USDT")
        except BinanceAPIException as e:
            self.logger.log_error(e, "while connecting to Binance API")
            raise
        
        self.validator = OrderValidator()
        
    
    def get_symbol_info(self, symbol: str) -> Dict:
        try:
            symbol = self.validator.validate_symbol(symbol)
            exchange_info = self.client.futures_exchange_info()
            
            for s in exchange_info['symbols']:
                if s['symbol'] == symbol:
                    return s
            raise ValueError(f"Symbol {symbol} not found in exchange info.")
        
        except Exception as e:
            self.logger.log_error(e, f"failed to get symbol info for {symbol}")
            raise
        
    
    def format_quantity(self, symbol: str, quantity: float) -> str:
        try:
            symbol_info = self.get_symbol_info(symbol)
            lot_size_filter = None
            for f in symbol_info['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    lot_size_filter = f
                    break
            
            if lot_size_filter:
                step_size = Decimal(lot_size_filter['stepSize'])
                quantity_decimal = Decimal(str(quantity))
                
                formatted_quantity = quantity_decimal.quantize(step_size, rounding=ROUND_DOWN)
                return str(formatted_quantity)
            
            return str(quantity)
            
        except Exception as e:
            self.logger.log_error(e, f"Failed to format quantity for {symbol}")
            return str(quantity)
        
    def format_price(self, symbol: str, price: float) -> str:
        try:
            symbol_info = self.get_symbol_info(symbol)
            
            price_filter = None
            for f in symbol_info['filters']:
                if f['filterType'] == 'PRICE_FILTER':
                    price_filter = f
                    break

            if price_filter:
                tick_size = Decimal(price_filter['tickSize'])
                price_decimal = Decimal(str(price))
                
                formatted_price = price_decimal.quantize(tick_size, rounding=ROUND_DOWN)
                return str(formatted_price)
            
            return f"{price:.2f}"  
        except Exception as e:
            self.logger.log_error(e, f"Failed to format price for {symbol}")
            return f"{price:.2f}"
        
        
    def place_market_order(self, symbol: str, side: str, quantity: float) -> Dict:
        try:
            symbol = self.validator.validate_symbol(symbol)
            side = self.validator.validate_side(side)
            quantity = self.validator.validate_quantity(quantity)

            formatted_quantity = self.format_quantity(symbol, quantity)

            order_params = {
                'symbol':symbol,
                'side':side,
                'type':'MARKET',
                'quantity':formatted_quantity,
            }
            
            self.logger.log_api_request("place_market_order", order_params)
            
            order = self.client.futures_create_order(**order_params)
            
            self.logger.log_api_response("place_market_order", order)
            self.logger.log_order_placement(order)
            
            return order
        
        except BinanceAPIException as e:
            self.logger.log_error(e, "binance API error in market order")
            raise
        except Exception as e:
            self.logger.log_error(e, "unexpected error in market order")
            raise
    
    
    # Place a limit order    
    def place_limit_order(self, symbol: str, side: str, quantity: float, price: float) -> Dict:
        try:
            symbol=self.validator.validate_symbol(symbol)
            side=self.validator.validate_side(side)
            quantity= self.validator.validate_quantity(quantity)
            price=self.validator.validate_price(price)

            formatted_quantity = self.format_quantity(symbol, quantity)
            formatted_price = self.format_price(symbol, price)

            order_params = {
                'symbol':symbol,
                'side':side,
                'type': 'LIMIT',
                'timeInForce':'GTC',
                'quantity': formatted_quantity,
                'price':formatted_price,
            }
            
            self.logger.log_api_request("place_limit_order", order_params)
            
            order= self.client.futures_create_order(**order_params)
            
            self.logger.log_api_response("place_limit_order", order)
            self.logger.log_order_placement(order)
            
            return order
            
        except BinanceAPIException as e:
            self.logger.log_error(e, "binance API error in limit order")
            raise
        except Exception as e:
            self.logger.log_error(e, "unexpected error in limit order")
            raise
    
    # Place a stop-limit order
    def place_stop_limit_order(self, symbol: str, side: str, quantity: float, stop_price: float, limit_price: float) -> Dict:
        try:
            symbol = self.validator.validate_symbol(symbol)
            side= self.validator.validate_side(side)
            quantity= self.validator.validate_quantity(quantity)
            stop_price= self.validator.validate_price(stop_price)
            limit_price = self.validator.validate_price(limit_price)

            formatted_quantity = self.format_quantity(symbol, quantity)
            formatted_stop_price = self.format_price(symbol, stop_price)
            formatted_limit_price = self.format_price(symbol, limit_price)

            order_params = {
                'symbol':symbol,
                'side': side,
                'type':'STOP',
                'timeInForce': 'GTC',
                'quantity':formatted_quantity,
                'stopPrice':formatted_stop_price,
                'price':formatted_limit_price
            }

            self.logger.log_api_request("place_stop_limit_order", order_params)

            order = self.client.futures_create_order(**order_params)

            self.logger.log_api_response("place_stop_limit_order", order)
            self.logger.log_order_placement(order)

            return order

        except BinanceAPIException as e:
            self.logger.log_error(e, "Binance API error in stop limit order")
            raise
        except Exception as e:
            self.logger.log_error(e, "Unexpected error in stop limit order")
            raise
        
        
    def cancel_order(self, symbol: str, order_id: int) -> Dict:
        try:
            symbol =self.validator.validate_symbol(symbol)

            result = self.client.futures_cancel_order(
                symbol=symbol,
                orderId=order_id
            )
            
            self.logger.logger.info(f"Order {order_id} cancelled for {symbol}: {result}")
            return result
        except Exception as e:
            self.logger.log_error(e, f"Failed to cancel order {order_id} for {symbol}")
            raise
        
    def get_order_status(self, symbol: str, order_id: int) -> Dict:
        try:
            symbol= self.validator.validate_symbol(symbol)
            order =self.client.futures_get_order(
                symbol=symbol,
                orderId=order_id
            )
            self.logger.log_api_response("get_order_status", order)
            return order
            
        except Exception as e:
            self.logger.log_error(e, f"Failed to get order status for {order_id}")
            raise
        
    
    def get_account_balance(self) -> Dict:
        try:
            account = self.client.futures_account()
            

            print(f"DEBUG - Account keys: {list(account.keys())}")
            
            balance_info = {
                'totalWalletBalance': account.get('totalWalletBalance', 
                                                account.get('balance', '0')),
                'totalUnrealizedPnl': account.get('totalUnrealizedPnl', '0'),
                'totalMarginBalance': account.get('totalMarginBalance', 
                                                account.get('totalWalletBalance', 
                                                        account.get('balance', '0'))),
                'availableBalance': account.get('availableBalance', 
                                            account.get('totalWalletBalance',
                                                        account.get('balance', '0')))
                                            }
            
            self.logger.log_api_response("get_account_balance", balance_info)
            return balance_info
        
        except Exception as e:
            self.logger.log_error(e, "Failed to get account balance")
            raise
    
    
    def get_current_price(self, symbol: str) -> float:
        try:
            symbol = self.validator.validate_symbol(symbol)
            ticker = self.client.futures_ticker(symbol=symbol)
            
            if isinstance(ticker, dict):
                for price_field in ['lastPrice', 'price', 'close']:
                    if price_field in ticker:
                        return float(ticker[price_field])
            
            elif isinstance(ticker, list) and len(ticker) > 0:
                ticker_item = ticker[0]
                for price_field in ['lastPrice', 'price', 'close']:
                    if price_field in ticker_item:
                        return float(ticker_item[price_field])
        
            mark_price = self.client.futures_mark_price(symbol=symbol)
            if 'markPrice' in mark_price:
                return float(mark_price['markPrice'])
            
            raise Exception(f"Could not get price for {symbol}")
            
        except Exception as e:
            self.logger.log_error(e, f"Failed to get current price for {symbol}")
            raise
        
#command line interface for the bot

class TradingBotCLI:

    def __init__(self,bot : BasicBot):
        self.bot = bot
        
    def display_menu(slef):
        
        print("\n"+"*"*50)
        print("Welcome to the Binance Trading Bot CLI")
        print("*"*50+"\n")
        print("1. Place Market Order")
        print("2. Place Limit Order")
        print("3. Place Stop Limit Order")
        print("4. check order status")
        print("5. cancel order")
        print("6. get account balance")
        print("7. get current price")
        print("8. Exit")
        print("\n"+"*"*50)
        
    
    def get_user_input(self, prompt: str,input_type: str,validator=None):
        while True:
            try:
                value = input(prompt)
                if input_type != str:
                    value = input_type(value)
                
                if validator:
                    value = validator(value)
                
                return value
                
            except (ValueError, TypeError) as e:
                print(f"Invalid input: {e}. Please try again.")
            except Exception as e:
                print(f"Error: {e}. Please try again.")
    
    def handle_market_order(self):
        try:
            symbol = self.get_user_input("Enter symbol (e.g., BTCUSDT): ")
            side = self.get_user_input("Enter side (BUY/SELL): ").strip().upper()
            quantity = self.get_user_input("Enter quantity: ", float)
            
            current_price= self.bot.get_current_price(symbol)
            print(f"Current price for {symbol} : ${current_price:.2f}")
            
            confirm = input(f"Confirm {side} {quantity} {symbol} at market price? (y/N): ")
            if confirm.lower() == 'y':
                order = self.bot.place_market_order(symbol, side, quantity)
                print(f"\n✅ Market order placed successfully!")
                print(f"Order ID: {order['orderId']}")
                print(f"Status: {order['status']}")
            else:
                print("Order cancelled.")
                
        except Exception as e:
            print(f"Error placing market order: {e}")
    
    
    def handle_limit_order(self):
        try:
            symbol=self.get_user_input("Enter symbol (e.g., BTC): ")
            side=self.get_user_input("Enter side (BUY/SELL): ").upper()
            quantity=self.get_user_input("enter quantity: ", float)
            price=self.get_user_input("enter limit price: ", float)
            
            current_price = self.bot.get_current_price(symbol)
            print(f"current price for {symbol}: ${current_price:.2f}")
            print(f"Your limit price: ${price:.2f}")
            
            confirm = input(f"Confirm {side} {quantity} {symbol} at ${price}? (y/N): ")
            if confirm.lower() == 'y':
                order = self.bot.place_limit_order(symbol, side, quantity, price)
                print(f"\nLimit order placed successfully!")
                print(f"order ID: {order['orderId']}")
                print(f"Status: {order['status']}")
            else:
                print("order cancelled.")    
        except Exception as e:
            print(f"error placing limit order: {e}")
    
    def handle_stop_limit_order(self):
        try:
            symbol=self.get_user_input("enter symbol (e.g., BTC): ")
            side=self.get_user_input("enter side (BUY/SELL): ").upper()
            quantity=self.get_user_input("Enter quantity: ", float)
            stop_price=self.get_user_input("enter stop price: ", float)
            limit_price=self.get_user_input("enter limit price: ", float)
            
            current_price = self.bot.get_current_price(symbol)
            print(f"current price for {symbol}: ${current_price:.2f}")
            print(f"stop price: ${stop_price:.2f}")
            print(f"limit price: ${limit_price:.2f}")
            
            confirm = input(f"Confirm stop-limit order? (y/N): ")
            if confirm.lower() == 'y':
                order = self.bot.place_stop_limit_order(symbol, side, quantity, stop_price, limit_price)
                print(f"\nStop-limit order placed successfully!")
                print(f"Order ID: {order['orderId']}")
                print(f"Status: {order['status']}")
            else:
                print("Order cancelled.")
                
        except Exception as e:
            print(f"error placing stop-limit order: {e}")
    
    def handle_order_status(self):
        try:
            symbol = self.get_user_input("enter symbol (e.g., BTC): ")
            order_id = self.get_user_input("enter order ID: ", int)
            
            order = self.bot.get_order_status(symbol, order_id)
            print(f"\nOrder Status:")
            print(f"Order ID: {order['orderId']}")
            print(f"Symbol: {order['symbol']}")
            print(f"Side: {order['side']}")
            print(f"Type: {order['type']}")
            print(f"Status: {order['status']}")
            print(f"Quantity: {order['origQty']}")
            print(f"Executed Quantity: {order['executedQty']}")
            
        except Exception as e:
            print(f"error getting order status: {e}")
    
    def handle_cancel_order(self):
        try:
            symbol = self.get_user_input("enter symbol (e.g., BTC): ")
            order_id = self.get_user_input("enter order ID: ", int)
            
            confirm = input("confirm cancellation? (y/N): ")
            if confirm.lower() == 'y':
                result = self.bot.cancel_order(symbol, order_id)
                print(f"order {order_id} cancelled successfully!")
            else:
                print("cancellation aborted.")
                
        except Exception as e:
            print(f"error cancelling order: {e}")
    
    def handle_account_balance(self):
        try:
            balance = self.bot.get_account_balance()
            
            print(f"account Summary:")
            print(f"total Wallet Balance: ${float(balance['totalWalletBalance']):.2f} USDT")
            print(f"available Balance: ${float(balance['availableBalance']):.2f} USDT")
            print(f"total Margin Balance: ${float(balance['totalMarginBalance']):.2f} USDT")
            print(f"unrealized PnL: ${float(balance['totalUnrealizedPnl']):.2f} USDT")
            
        except Exception as e:
            print(f"error getting account balance: {e}")
    
    def handle_current_price(self):
        try:
            symbol = self.get_user_input("Enter symbol (e.g., BTC): ")
            
            price = self.bot.get_current_price(symbol)
            print(f"current price for {symbol.upper()}: ${price:.2f}")
            
        except Exception as e:
            print(f"error getting current price: {e}")
    
    def run(self):
        print("welcome to Binance Futures Trading Bot!")
        print("connected to Testnet" if self.bot.testnet else "⚠️  Connected to LIVE trading")
        
        while True:
            try:
                self.display_menu()
                choice = input("\nSelect option (1-8): ").strip()
                
                if choice == '1':
                    self.handle_market_order()
                elif choice == '2':
                    self.handle_limit_order()
                elif choice == '3':
                    self.handle_stop_limit_order()
                elif choice == '4':
                    self.handle_order_status()
                elif choice == '5':
                    self.handle_cancel_order()
                elif choice == '6':
                    self.handle_account_balance()
                elif choice == '7':
                    self.handle_current_price()
                elif choice == '8':
                    print("Happy trading!")
                    break
                else:
                    print("invalid option. Please select 1-8.")
                
                input("\nPress Enter to continue...")
                
            except KeyboardInterrupt:
                print("\n\nGoodbye! Happy trading!")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")


def main():
    if CONFIG_AVAILABLE:
        try:
            bot = BasicBot(BINANCE_API_KEY, BINANCE_API_SECRET, DEFAULT_TESTNET)
            cli = TradingBotCLI(bot)
            cli.run()
        except Exception as e:
            print(f"failed to start trading bot: {e}")
            sys.exit(1)
    else:
        parser = argparse.ArgumentParser(description='Binance Futures Trading Bot')
        parser.add_argument('--api-key', required=True, help='Binance API key')
        parser.add_argument('--api-secret', required=True, help='Binance API secret')
        parser.add_argument('--live', action='store_true', help='Use live trading (default: testnet)')
        
        args = parser.parse_args()
        
        try:
            bot = BasicBot(args.api_key, args.api_secret, testnet=not args.live)
            cli = TradingBotCLI(bot)
            cli.run()
        except Exception as e:
            print(f"Failed to start trading bot: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()