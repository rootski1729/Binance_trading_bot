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