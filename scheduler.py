import logging
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
    try:
        signal = ta.rsi_ma_signal()
        if signal['signal'] != "HOLD":
            # In production, you'd loop through whitelisted users
            # For now, just log
            logging.info(f"Auto signal: {signal['signal']} for {signal['symbol']}")
    except Exception as e:
        logging.error(f"Auto trade job error: {e}")

async def price_monitor_job():
    """Monitor price and RSI for alerts - fixed symbol handling"""
    from bot import bot, alert_manager  # import here to avoid circular
    symbol = "BTCUSDT"
    try:
        # Get current price safely
        price = ta.client.get_symbol_price(symbol)
        await alert_manager.check_price_alerts(symbol, price)
        
        # Get RSI safely
        rsi = ta.get_rsi(symbol)
        await alert_manager.check_rsi_alerts(symbol, rsi)
    except Exception as e:
        logging.error(f"Price monitor error for {symbol}: {e}")

def start_scheduler():
    scheduler.add_job(auto_trade_job, IntervalTrigger(minutes=5))
    scheduler.add_job(price_monitor_job, IntervalTrigger(seconds=30))
    scheduler.start()
    logging.info("Scheduler started")
