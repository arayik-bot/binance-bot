from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from analysis import TechnicalAnalysis
from alerts import AlertManager
from trading import TradingBot
import config

scheduler = AsyncIOScheduler()
ta = TechnicalAnalysis()
trading_bot = TradingBot()

async def auto_trade_job():
    signal = ta.rsi_ma_signal()
    if signal['signal'] != "HOLD":
        # Trigger confirmation flow for all active users (simplified)
        from bot import bot, alert_manager
        # In production, you'd loop through whitelisted users
        # For now, just send to a default user (you can store active users)
        pass

async def price_monitor_job():
    from bot import bot, alert_manager
    price = ta.client.get_symbol_price("BTCUSDT")
    await alert_manager.check_price_alerts("BTCUSDT", price)
    rsi = ta.get_rsi("BTCUSDT")
    await alert_manager.check_rsi_alerts("BTCUSDT", rsi)

def start_scheduler():
    scheduler.add_job(auto_trade_job, IntervalTrigger(minutes=5))
    scheduler.add_job(price_monitor_job, IntervalTrigger(seconds=30))
    scheduler.start()
