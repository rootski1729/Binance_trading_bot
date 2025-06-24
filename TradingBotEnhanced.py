
import os
import sys
import logging
import json
import time
from datetime import datetime
from typing import Dict, Optional, List
from decimal import Decimal, ROUND_DOWN
import argparse

try:
    from binance import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
except ImportError:
    print("ERROR: python-binance library not found")
    sys.exit(1)


try:
    from config import (
        BINANCE_API_KEY, BINANCE_API_SECRET, DEFAULT_TESTNET,
        MAX_ORDER_VALUE_USDT, MIN_ORDER_QUANTITY, REQUEST_DELAY
    )
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    print("config file not found")


class TradingBotLogger:
    def __init__(self, log_level=logging.INFO):
        self.logger = logging.getLogger('TradingBot')
        self.logger.setLevel(log_level)
    
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        file_handler = logging.FileHandler(
            f'logs/trading_bot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        )
        file_handler.setLevel(logging.DEBUG)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def log_api_request(self, method: str, params: Dict):
        safe_params = params.copy()
        if 'signature' in safe_params:
            safe_params['signature'] = '[REDACTED]'
        
        self.logger.info(f"API REQUEST - {method}: {json.dumps(safe_params, indent=2)}")
    
    def log_api_response(self, method: str, response: Dict):
        self.logger.info(f"API RESPONSE - {method}: {json.dumps(response, indent=2)}")
    
    def log_error(self, error: Exception, context: str = ""):
        self.logger.error(f"ERROR {context}: {str(error)}")
    
    def log_order_placement(self, order_details: Dict):

        self.logger.info(f"ORDER PLACED: {json.dumps(order_details, indent=2)}")
    
    # Safety check logging
    def log_safety_check(self, check_type: str, result: bool, details: str = ""):
        status = "PASSED" if result else "FAILED"
        self.logger.warning(f"SAFETY CHECK {status} - {check_type}: {details}")


class OrderValidator:
    # Order validation and safety checks  
    def __init__(self, max_order_value: float = 1000.0, min_quantity: float = 0.001):
        self.max_order_value = max_order_value
        self.min_quantity = min_quantity
    
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
    
    def validate_quantity(self, quantity: float) -> float:
        if quantity <= 0:
            raise ValueError(f"Invalid quantity: {quantity}. Must be positive")
        if quantity < self.min_quantity:
            raise ValueError(f"Quantity {quantity} below minimum {self.min_quantity}")
        return quantity
    
    def validate_price(self, price: float) -> float:
        if price <= 0:
            raise ValueError(f"Invalid price: {price}. Must be positive")
        return price
    
    def validate_order_value(self, quantity: float, price: float) -> bool:
        order_value = quantity * price
        if order_value > self.max_order_value:
            raise ValueError(
                f"Order value ${order_value:.2f} exceeds maximum ${self.max_order_value:.2f}"
            )
        return True


class EnhancedTradingBot:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True, 
                max_order_value: float = 1000.0):
        
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.max_order_value = max_order_value
        
        self.logger = TradingBotLogger()
        self.validator = OrderValidator(max_order_value=max_order_value)
        
        self.last_request_time = 0
        self.request_delay = REQUEST_DELAY if CONFIG_AVAILABLE else 0.1
        
        try:
            self.client = Client(
                api_key=api_key,
                api_secret=api_secret,
                testnet=testnet
            )
            
            self.client.ping()
            self.logger.logger.info("Successfully connected to Binance API")
            
            account_info = self.client.futures_account()
            balance = account_info.get('totalWalletBalance', account_info.get('balance', '0'))
            self.logger.logger.info(f"Account balance: {balance} USDT")
            
            self.logger.logger.info(f"Max order value: ${max_order_value:.2f}")
            self.logger.logger.info(f"Testnet mode: {testnet}")
            
        except Exception as e:
            self.logger.log_error(e, "Failed to initialize Binance client")
            raise
    
    def _rate_limit(self):
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.request_delay:
            sleep_time = self.request_delay - time_since_last_request
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _safety_check_order(self, symbol: str, side: str, quantity: float, 
                        price: Optional[float] = None) -> bool:
        try:
            if price is None:
                current_price = self.get_current_price(symbol)
            else:
                current_price = price
        
            order_value = quantity * current_price

            self.logger.log_safety_check(
                "ORDER_VALUE", 
                order_value <= self.max_order_value,
                f"Order value: ${order_value:.2f}, Max: ${self.max_order_value:.2f}"
            )

            self.validator.validate_order_value(quantity, current_price)
            
            return True
            
        except Exception as e:
            self.logger.log_safety_check(
                "ORDER_VALIDATION", 
                False, 
                f"Failed: {str(e)}"
            )
            raise
    
    def get_symbol_info(self, symbol: str) -> Dict:
        try:
            symbol = self.validator.validate_symbol(symbol)
            self._rate_limit()
            exchange_info = self.client.futures_exchange_info()
            
            for s in exchange_info['symbols']:
                if s['symbol'] == symbol:
                    return s
            raise ValueError(f"Symbol {symbol} not found")
        except Exception as e:
            self.logger.log_error(e, f"faailed to get symbol info for {symbol}")
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
            self.logger.log_error(e, f"failed to format quantity for {symbol}")
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
            self.logger.log_error(e, f"failed to format price for {symbol}")
            return f"{price:.2f}"
    
    def place_market_order(self, symbol: str, side: str, quantity: float) -> Dict:
        try:
            symbol = self.validator.validate_symbol(symbol)
            side = self.validator.validate_side(side)
            quantity = self.validator.validate_quantity(quantity)
        
            self._safety_check_order(symbol, side, quantity)
            
            formatted_quantity = self.format_quantity(symbol, quantity)
            order_params = {
                'symbol':symbol,
                'side':side,
                'type':'MARKET',
                'quantity':formatted_quantity
            }
            
            self.logger.log_api_request("place_market_order", order_params)
            self._rate_limit()
            order = self.client.futures_create_order(**order_params)
            
            self.logger.log_api_response("place_market_order", order)
            self.logger.log_order_placement(order)
            
            return order
            
        except Exception as e:
            self.logger.log_error(e, "error in market order")
            raise
    
    def place_limit_order(self, symbol: str, side: str, quantity: float, price: float) -> Dict:
        try:
            symbol = self.validator.validate_symbol(symbol)
            side = self.validator.validate_side(side)
            quantity = self.validator.validate_quantity(quantity)
            price = self.validator.validate_price(price)
            
            self._safety_check_order(symbol, side, quantity, price)
        
            formatted_quantity = self.format_quantity(symbol, quantity)
            formatted_price = self.format_price(symbol, price)
            
            order_params = {
                'symbol':symbol,
                'side':side,
                'type':'LIMIT',
                'quantity':formatted_quantity,
                'price':formatted_price,
                'timeInForce': 'GTC'
            }
            
            self.logger.log_api_request("place_limit_order", order_params)
            self._rate_limit()
            
            order = self.client.futures_create_order(**order_params)
            
            self.logger.log_api_response("place_limit_order", order)
            self.logger.log_order_placement(order)
            
            return order
            
        except Exception as e:
            self.logger.log_error(e, "error in limit order")
            raise
    
    def place_stop_limit_order(self, symbol: str, side: str, quantity: float, 
                            stop_price: float, limit_price: float) -> Dict:
        try:
            symbol = self.validator.validate_symbol(symbol)
            side = self.validator.validate_side(side)
            quantity = self.validator.validate_quantity(quantity)
            stop_price = self.validator.validate_price(stop_price)
            limit_price = self.validator.validate_price(limit_price)
        
            self._safety_check_order(symbol, side, quantity, limit_price)
            

            formatted_quantity = self.format_quantity(symbol, quantity)
            formatted_stop_price = self.format_price(symbol, stop_price)
            formatted_limit_price = self.format_price(symbol, limit_price)
            
            order_params = {
                'symbol':symbol,
                'side':side,
                'type':'STOP',
                'quantity':formatted_quantity,
                'price': formatted_limit_price,
                'stopPrice':formatted_stop_price,
                'timeInForce':'GTC'
            }
            self.logger.log_api_request("place_stop_limit_order", order_params)
            self._rate_limit()
            order = self.client.futures_create_order(**order_params)
            
            self.logger.log_api_response("place_stop_limit_order", order)
            self.logger.log_order_placement(order)
            
            return order
            
        except Exception as e:
            self.logger.log_error(e, "error in stop-limit order")
            raise
    
    def get_current_price(self, symbol: str) -> float:
        try:
            symbol = self.validator.validate_symbol(symbol)
            self._rate_limit()
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
    
    def get_account_balance(self) -> Dict:
        try:
            self._rate_limit()
            account = self.client.futures_account()
            balance_info = {
                'totalWalletBalance': account.get('totalWalletBalance', '0'),
                'totalUnrealizedPnl': account.get('totalUnrealizedPnl', '0'),
                'totalMarginBalance': account.get('totalMarginBalance', 
                                                account.get('totalWalletBalance', '0')),
                'availableBalance': account.get('availableBalance', 
                                            account.get('totalWalletBalance', '0'))
            }
            
            self.logger.log_api_response("get_account_balance", balance_info)
            return balance_info
            
        except Exception as e:
            self.logger.log_error(e, "faailed to get account balance")
            raise


def main():
    parser = argparse.ArgumentParser(description='Enhanced Binance Futures Trading Bot')
    
    if CONFIG_AVAILABLE:
        parser.add_argument('--api-key', default=BINANCE_API_KEY, help='Binance API key')
        parser.add_argument('--api-secret', default=BINANCE_API_SECRET, help='Binance API secret')
        parser.add_argument('--testnet', action='store_true', default=DEFAULT_TESTNET, 
                        help='use testnet (default from config)')
        parser.add_argument('--max-order-value', type=float, default=MAX_ORDER_VALUE_USDT,
                        help='max order value in dollars')
    else:
        parser.add_argument('--api-key', required=True, help='Binance API key')
        parser.add_argument('--api-secret', required=True, help='Binance API secret')
        parser.add_argument('--testnet', action='store_true', default=True, help='Use testnet')
        parser.add_argument('--max-order-value', type=float, default=1000.0,
                        help='max order value in dollar')
    
    args = parser.parse_args()
    
    try:
        print(f"configuration: {'Config file' if CONFIG_AVAILABLE else 'Command line'}")
        print(f"mode: {'Testnet' if args.testnet else 'LIVE TRADING'}")
        print(f"max order value: ${args.max_order_value:.2f}")
        
        if not args.testnet:
            confirm = input("type 'CONFIRM' to go live trading: ").strip().upper()
            if confirm != 'CONFIRM':
                print("aborted. Use --testnet for safe testing.")
                return
        bot = EnhancedTradingBot(
            api_key=args.api_key,
            api_secret=args.api_secret,
            testnet=args.testnet,
            max_order_value=args.max_order_value
        )
        
        print("enhanced Trading Bot initialized successfully!")
        print("check the logs")
        
        balance = bot.get_account_balance()
        print(f"account Balance: ${float(balance['totalWalletBalance']):.2f} USDT")
        
        
    except Exception as e:
        print(f"failed to start enhanced trading bot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()