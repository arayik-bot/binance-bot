import pandas as pd
import numpy as np
import ta
from binance_client import BinanceClient
import config

class TechnicalAnalysis:
    def __init__(self):
        self.client = BinanceClient()
    
    def get_rsi(self, symbol="BTCUSDT", period=14):
        klines = self.client.get_klines(symbol, limit=period+1)
        df = pd.DataFrame(klines, columns=['time','open','high','low','close','volume','close_time','quote_asset_volume','number_of_trades','taker_buy_base','taker_buy_quote','ignore'])
        df['close'] = df['close'].astype(float)
        rsi = ta.momentum.RSIIndicator(close=df['close'], window=period).rsi().iloc[-1]
        return round(rsi, 2)
    
    def get_ma(self, symbol="BTCUSDT", window=14):
        klines = self.client.get_klines(symbol, limit=window+1)
        df = pd.DataFrame(klines, columns=['time','open','high','low','close','volume','close_time','quote_asset_volume','number_of_trades','taker_buy_base','taker_buy_quote','ignore'])
        df['close'] = df['close'].astype(float)
        ma = df['close'].rolling(window=window).mean().iloc[-1]
        return round(ma, 2)
    
    def rsi_ma_signal(self, symbol="BTCUSDT"):
        rsi = self.get_rsi(symbol, config.RSI_PERIOD)
        ma_short = self.get_ma(symbol, config.MA_SHORT)
        ma_long = self.get_ma(symbol, config.MA_LONG)
        current_price = self.client.get_symbol_price(symbol)
        
        signal = "HOLD"
        if rsi < config.RSI_OVERSOLD and ma_short > ma_long:
            signal = "BUY"
        elif rsi > config.RSI_OVERBOUGHT and ma_short < ma_long:
            signal = "SELL"
        
        return {
            "symbol": symbol,
            "price": current_price,
            "rsi": rsi,
            "ma_short": ma_short,
            "ma_long": ma_long,
            "signal": signal
        }
