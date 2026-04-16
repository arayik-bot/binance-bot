import asyncio
from aiogram import Bot
import config

class AlertManager:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.price_alerts = {}  # {user_id: {symbol: target_price}}
        self.rsi_alerts = {}    # {user_id: {symbol: threshold}}
    
    async def check_price_alerts(self, symbol, current_price):
        for user_id, alerts in self.price_alerts.items():
            if symbol in alerts and current_price >= alerts[symbol]:
                await self.bot.send_message(user_id, f"🔔 Price alert: {symbol} reached ${current_price}")
                del self.price_alerts[user_id][symbol]
    
    async def check_rsi_alerts(self, symbol, rsi):
        for user_id, alerts in self.rsi_alerts.items():
            if symbol in alerts:
                if (alerts[symbol] == "overbought" and rsi >= config.RSI_OVERBOUGHT) or \
                   (alerts[symbol] == "oversold" and rsi <= config.RSI_OVERSOLD):
                    await self.bot.send_message(user_id, f"🔔 RSI alert: {symbol} RSI={rsi}")
                    del self.rsi_alerts[user_id][symbol]
    
    def set_price_alert(self, user_id, symbol, price):
        if user_id not in self.price_alerts:
            self.price_alerts[user_id] = {}
        self.price_alerts[user_id][symbol] = price
    
    def set_rsi_alert(self, user_id, symbol, condition):
        if user_id not in self.rsi_alerts:
            self.rsi_alerts[user_id] = {}
        self.rsi_alerts[user_id][symbol] = condition
