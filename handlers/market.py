from binance_client import BinanceClient
import config

class MarketData:
    def __init__(self):
        self.client = BinanceClient()
    
    def get_price(self, symbol="BTCUSDT"):
        return self.client.get_symbol_price(symbol)
    
    def get_stats(self, symbol="BTCUSDT"):
        return self.client.get_24h_stats(symbol)
    
    def get_top_gainers(self):
        tickers = self.client.client.get_ticker()
        gainers = sorted(tickers, key=lambda x: float(x['priceChangePercent']), reverse=True)[:5]
        return [(t['symbol'], t['priceChangePercent']) for t in gainers]
    
    def get_top_losers(self):
        tickers = self.client.client.get_ticker()
        losers = sorted(tickers, key=lambda x: float(x['priceChangePercent']))[:5]
        return [(t['symbol'], t['priceChangePercent']) for t in losers]
