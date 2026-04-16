import asyncio
import logging
from aiogram import Bot
import config

def normalize_symbol(symbol: str) -> str:
    """Normalize symbol to Binance format (uppercase, USDT quote)"""
    symbol = symbol.upper().replace("/", "").replace(" ", "")
    if not symbol.endswith("USDT"):
        symbol += "USDT"
    return symbol

class AlertManager:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.price_alerts = {}  # {user_id: {normalized_symbol: target_price}}
        self.rsi_alerts = {}    # {user_id: {normalized_symbol: condition}}
    
    async def check_price_alerts(self, symbol, current_price):
        symbol = normalize_symbol(symbol)
        for user_id, alerts in self.price_alerts.items():
            if symbol in alerts and current_price >= alerts[symbol]:
                try:
                    await self.bot.send_message(user_id, f"🔔 Price alert: {symbol} reached ${current_price}")
                    del self.price_alerts[user_id][symbol]
                except Exception as e:
                    logging.error(f"Failed to send price alert: {e}")
    
    async def check_rsi_alerts(self, symbol, rsi):
        symbol = normalize_symbol(symbol)
        for user_id, alerts in self.rsi_alerts.items():
            if symbol in alerts:
                condition = alerts[symbol]
                triggered = False
                if condition == "overbought" and rsi >= config.RSI_OVERBOUGHT:
                    triggered = True
                elif condition == "oversold" and rsi <= config.RSI_OVERSOLD:
                    triggered = True
                if triggered:
                    try:
                        await self.bot.send_message(user_id, f"🔔 RSI alert: {symbol} RSI={rsi}")
                        del self.rsi_alerts[user_id][symbol]
                    except Exception as e:
                        logging.error(f"Failed to send RSI alert: {e}")
    
    def set_price_alert(self, user_id, symbol, price):
        symbol = normalize_symbol(symbol)
        if user_id not in self.price_alerts:
            self.price_alerts[user_id] = {}
        self.price_alerts[user_id][symbol] = price
    
    def set_rsi_alert(self, user_id, symbol, condition):
        symbol = normalize_symbol(symbol)
        if user_id not in self.rsi_alerts:
            self.rsi_alerts[user_id] = {}
        self.rsi_alerts[user_id][symbol] = condition
    
    def get_alerts(self, user_id):
        return {
            "price": self.price_alerts.get(user_id, {}),
            "rsi": self.rsi_alerts.get(user_id, {})
        }
