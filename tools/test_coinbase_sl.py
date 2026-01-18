import os
import ccxt
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_sl")

def test_sl():
    api_key = os.getenv("CCXT_API_KEY") or os.getenv("COINBASE_API_KEY") or os.getenv("CB_ACCESS_KEY")
    api_secret = os.getenv("CCXT_SECRET") or os.getenv("COINBASE_API_SECRET") or os.getenv("CB_ACCESS_SECRET")
    
    if not (api_key and api_secret):
        logger.error("No API keys found")
        return

    exchange = ccxt.coinbase({
        "apiKey": api_key,
        "secret": api_secret,
    })

    symbol = "ETH/USD"
    # Get current price to set a safe stop (way below market)
    ticker = exchange.fetch_ticker(symbol)
    last_price = ticker["last"]
    stop_price = last_price * 0.5 # 50% below, safe test
    limit_price = stop_price * 0.95 # aggressive limit
    
    amount = 0.001
    f_stop = exchange.price_to_precision(symbol, stop_price)
    f_limit = exchange.price_to_precision(symbol, limit_price)

    logger.info(f"Last: {last_price}, Stop: {stop_price}, Limit: {limit_price}")

    try:
        logger.info("--- Testing type: limit with stop_direction ---")
        # For Coinbase Advanced:
        # We want a Sell Stop (Down)
        params = {
            "stop_price": f_stop,
            "stop_direction": "STOP_DIRECTION_STOP_DOWN", 
        }
        
        logger.info(f"Calling create_order({symbol}, 'limit', 'sell', {amount}, {f_limit}, {params})")
        order = exchange.create_order(symbol, "limit", "sell", amount, float(f_limit), params)
        logger.info(f"SUCCESS! Order ID: {order['id']}")
        exchange.cancel_order(order["id"], symbol)
        logger.info("Cancelled.")
    except Exception as e:
        logger.error(f"Failed: {e}")

if __name__ == "__main__":
    test_sl()
