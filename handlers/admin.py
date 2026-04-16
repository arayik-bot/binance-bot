from aiogram import types
from aiogram.dispatcher import Dispatcher
import config

async def cmd_start(message: types.Message):
    if message.from_user.id not in config.ALLOWED_USER_IDS:
        await message.answer("⛔ Access denied.")
        return
    await message.answer("🚀 Binance Trading Bot is active!\nUse /help for commands.")

async def cmd_help(message: types.Message):
    help_text = """
📋 *Available Commands*:
/price <symbol> - Get current price
/stats <symbol> - 24h stats
/rsi <symbol> - RSI value
/signal - RSI+MA signal
/balance - Portfolio summary
/alert_price <symbol> <price> - Set price alert
/alert_rsi <symbol> overbought/oversold - Set RSI alert
/start_trading - Enable auto-trading
/stop_trading - Disable auto-trading
/buy <amount_usd> - Buy BTC with confirmation
/sell <amount_usd> - Sell BTC
    """
    await message.answer(help_text, parse_mode="Markdown")

async def cmd_start_trading(message: types.Message):
    from trading import trading_bot
    trading_bot.trading_enabled = True
    await message.answer("✅ Auto-trading enabled.")

async def cmd_stop_trading(message: types.Message):
    from trading import trading_bot
    trading_bot.trading_enabled = False
    await message.answer("❌ Auto-trading disabled.")

def register_admin_handlers(dp: Dispatcher):
    dp.message.register(cmd_start, commands=["start"])
    dp.message.register(cmd_help, commands=["help"])
    dp.message.register(cmd_start_trading, commands=["start_trading"])
    dp.message.register(cmd_stop_trading, commands=["stop_trading"])
