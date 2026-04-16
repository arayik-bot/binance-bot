from binance.client import Client
from binance.exceptions import BinanceAPIException
import config

class BinanceClient:
    def __init__(self):
        self.client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET_KEY)
    
    def get_klines(self, symbol="BTCUSDT", interval=Client.KLINE_INTERVAL_15MINUTE, limit=100):
        return self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
    
    def get_symbol_price(self, symbol="BTCUSDT"):
        ticker = self.client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    
    def get_24h_stats(self, symbol="BTCUSDT"):
        stats = self.client.get_ticker(symbol=symbol)
        return {
            'price': float(stats['lastPrice']),
            'change_24h': float(stats['priceChangePercent']),
            'volume': float(stats['volume']),
            'high': float(stats['highPrice']),
            'low': float(stats['lowPrice'])
        }
    
    def create_market_order(self, symbol, side, quantity):
        if config.READ_ONLY_MODE:
            return {"error": "Read-only mode active"}
        try:
            order = self.client.create_order(
                symbol=symbol,
                side=side,
                type=Client.ORDER_TYPE_MARKET,
                quantity=quantity
            )
            return order
        except BinanceAPIException as e:
            return {"error": str(e)}
    
    def get_account_balance(self, asset=None):
        acc = self.client.get_account()
        balances = {}
        for bal in acc['balances']:
            free = float(bal['free'])
            locked = float(bal['locked'])
            if free > 0 or locked > 0:
                balances[bal['asset']] = {'free': free, 'locked': locked}
        if asset:
            return balances.get(asset, {'free': 0, 'locked': 0})
        return balances
    
    def get_open_orders(self, symbol=None):
        return self.client.get_open_orders(symbol=symbol)
    
    def get_trade_history(self, symbol="BTCUSDT", limit=50):
        return self.client.get_my_trades(symbol=symbol, limit=limit)
