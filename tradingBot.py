import os
import sys
import logging
import json
from datetime import datetime
from typing import Dict, optional
from decimal import Decimal, ROUND_DOWN

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
        
    def place_market_order(self, symbol: str, side: str, quantity: float) -> Dict:
        try:
            symbol = self.validator.validate_symbol(symbol)
            side = self.validator.validate_side(side)
            quantity = self.validator.validate_quantity(quantity)

            formatted_quantity = self.format_quantity(symbol, quantity)

            order_params = {
                'symbol': symbol,
                'side': side,
                'type': 'MARKET',
                'quantity': formatted_quantity,
            }
            
            self.logger.log_api_request("place_market_order", order_params)
            
            order = self.client.futures_create_order(**order_params)
            
            self.logger.log_api_response("place_market_order", order)
            self.logger.log_order_placement(order)
            
            return order
        
        except BinanceAPIException as e:
            self.logger.log_error(e, "Binance API error in market order")
            raise
        except Exception as e:
            self.logger.log_error(e, "Unexpected error in market order")
            raise
        
    def place_limit_order(self, symbol: str, side: str, quantity: float, price: float) -> Dict:
        try:
            symbol = self.validator.validate_symbol(symbol)
            side = self.validator.validate_side(side)
            quantity = self.validator.validate_quantity(quantity)
            price = self.validator.validate_price(price)

            formatted_quantity = self.format_quantity(symbol, quantity)

            order_params = {
                'symbol': symbol,
                'side': side,
                'type': 'LIMIT',
                'timeInForce': 'GTC',
                'quantity': formatted_quantity,
                'price': str(price),
            }
            
            self.logger.log_api_request("place_limit_order", order_params)
            
            order = self.client.futures_create_order(**order_params)
            
            self.logger.log_api_response("place_limit_order", order)
            self.logger.log_order_placement(order)
            
            return order
            
        except BinanceAPIException as e:
            self.logger.log_error(e, "Binance API error in limit order")
            raise
        except Exception as e:
            self.logger.log_error(e, "Unexpected error in limit order")
            raise