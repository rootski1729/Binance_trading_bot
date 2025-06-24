import sys
import time
from tradingBot import BasicBot

def test_connection(bot):
    print("Testing connection...")
    try:
        balance = bot.get_account_balance()
        print(f"connection successful!")
        print(f"account Balance: ${float(balance['totalWalletBalance']):.2f} USDT")
        return True
    except Exception as e:
        print(f"connection failed: {e}")
        return False

def test_price_fetching(bot):
    print("\n testing price fetching...")
    symbols = ['BTCUSDT', 'ETHUSDT', 'ADAUSDT']
    for symbol in symbols:
        try:
            price = bot.get_current_price(symbol)
            print(f"{symbol}: ${price:.2f}")
        except Exception as e:
            print(f"failed get price for {symbol}: {e}")
            return False
    
    return True

def test_market_order(bot, symbol='BTCUSDT', quantity=0.001):
    print(f"\n testing market order ({symbol})...")
    
    try:
        current_price = bot.get_current_price(symbol)
        print(f"current {symbol} price: ${current_price:.2f}")
        
        print(f"placing BUY market order: {quantity} {symbol}")
        order = bot.place_market_order(symbol, 'BUY', quantity)
        
        print(f"Market order placed successfully!")
        print(f"Order ID: {order['orderId']}")
        print(f"status: {order['status']}")
        
        order_status = bot.get_order_status(symbol, order['orderId'])
        print(f"final status: {order_status['status']}")
        
        if order_status['status'] == 'FILLED':
            print(f"executed quantity: {order_status['executedQty']}")
        
        return True, order['orderId']
        
    except Exception as e:
        print(f"market order test failed: {e}")
        return False, None

def test_limit_order(bot, symbol='ETHUSDT', quantity=0.01):
    print(f"\n testing limit order ({symbol})...")
    
    try:
        current_price = bot.get_current_price(symbol)
        
        limit_price = current_price * 0.95
        
        print(f"current {symbol} price: ${current_price:.2f}")
        print(f"placing BUY limit order: {quantity} {symbol} at ${limit_price:.2f}")
        
        order = bot.place_limit_order(symbol, 'BUY', quantity, limit_price)
        
        print(f"limit order placed successfully!")
        print(f"order ID: {order['orderId']}")
        print(f"status: {order['status']}")
        
        time.sleep(2)
        order_status = bot.get_order_status(symbol, order['orderId'])
        print(f"status after 2s: {order_status['status']}")

        if order_status['status'] in ['NEW', 'PARTIALLY_FILLED']:
            print("cancelling limit order...")
            cancel_result = bot.cancel_order(symbol, order['orderId'])
            print("order cancelled successfully")
        
        return True, order['orderId']
        
    except Exception as e:
        print(f"limit order test failed: {e}")
        return False, None

def test_error_handling(bot):
    print("\n testing error handling...")
    
    test_cases = [
        ("invalid symbol", lambda: bot.get_current_price("INVALIDUSDT")),
        ("invalid quantity", lambda: bot.place_market_order("BTCUSDT", "BUY", -1)),
        ("invalid side", lambda: bot.place_market_order("BTCUSDT", "INVALID", 0.001)),
    ]
    
    passed = 0
    for test_name, test_func in test_cases:
        try:
            test_func()
            print(f"{test_name}: Should have failed but didn't")
        except Exception as e:
            print(f"{test_name}: Correctly handled error - {type(e).__name__}")
            passed += 1
    
    return passed == len(test_cases)

def run_basic_tests():
    print("Binance Trading Bot")
    print("*" * 60)
    
    try:
        from config import BINANCE_API_KEY, BINANCE_API_SECRET, DEFAULT_TESTNET
        print("initializing bot...")
        bot = BasicBot(BINANCE_API_KEY, BINANCE_API_SECRET, DEFAULT_TESTNET)
        print("bot initialized successfully!\n")
        
        test_results = []
        
        # Test 1: connection
        test_results.append(("Connection Test", test_connection(bot)))
        
        # Test 2: price Fetching
        test_results.append(("Price Fetching", test_price_fetching(bot)))
        
        # Test 3: Mmarket order
        market_success, market_order_id = test_market_order(bot)
        test_results.append(("Market Order", market_success))
        
        # Test 4: limit Order
        limit_success, limit_order_id = test_limit_order(bot)
        test_results.append(("Limit Order", limit_success))
        
        # Test 5: Error Handling
        test_results.append(("Error Handling", test_error_handling(bot)))
        
        # final Results
        print("\n" + "*" * 60)
        print("results")
        print("*" * 60)
        
        passed = 0
        for test_name, result in test_results:
            status = "Passed" if result else "Failed"
            print(f"{test_name:<20} {status}")
            if result:
                passed += 1
        
        print(f"\n overall: {passed}/{len(test_results)} tests passed")
        
        if passed == len(test_results):
            print("all test passed!")
        else:
            print("some test failed, do review")
        print("\n final account Status:")
        balance = bot.get_account_balance()
        print(f"Total Wallet Balance: ${float(balance['totalWalletBalance']):.2f} USDT")
        
        return passed == len(test_results)
        
    except ImportError:
        print("Config file not found.")
        return False
    except Exception as e:
        print(f"test suite failed: {e}")
        return False

def main():
    print("starting automated tests...\n")
    success = run_basic_tests()
    
    if success:
        print("\n all tests completed successfully!")
        print("check the logs, for details")
    else:
        print("\n some tests failed. Please fix the issues.")
        sys.exit(1)

if __name__ == "__main__":
    main()