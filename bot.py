import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import config
from binance_client import BinanceClient
from market import MarketData
from analysis import TechnicalAnalysis
from portfolio import Portfolio
from alerts import AlertManager, normalize_symbol
from trading import TradingBot
from admin import register_admin_handlers
from scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

market = MarketData()
ta = TechnicalAnalysis()
portfolio = Portfolio()
alert_manager = AlertManager(bot)
trading_bot = TradingBot()

# FSM for custom amount input
class AmountInput(StatesGroup):
    waiting_for_custom_amount = State()

# ---------- COMMANDS ----------
@dp.message(lambda message: message.from_user.id in config.ALLOWED_USER_IDS, commands=["price"])
async def cmd_price(message: types.Message):
    parts = message.text.split()
    symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
    symbol = normalize_symbol(symbol)
    try:
        price = market.get_price(symbol)
        await message.answer(f"💰 {symbol}: ${price}")
    except Exception as e:
        await message.answer(f"❌ Error: {e}")

@dp.message(commands=["stats"])
async def cmd_stats(message: types.Message):
    parts = message.text.split()
    symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
    symbol = normalize_symbol(symbol)
    try:
        stats = market.get_stats(symbol)
        text = f"📊 *{symbol} 24h Stats*\n"
        text += f"Price: ${stats['price']}\n"
        text += f"Change: {stats['change_24h']}%\n"
        text += f"Volume: ${stats['volume']:,.0f}\n"
        text += f"High: ${stats['high']}\n"
        text += f"Low: ${stats['low']}"
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Error: {e}")

@dp.message(commands=["rsi"])
async def cmd_rsi(message: types.Message):
    parts = message.text.split()
    symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
    symbol = normalize_symbol(symbol)
    try:
        rsi = ta.get_rsi(symbol)
        await message.answer(f"📈 {symbol} RSI(14): {rsi}")
    except Exception as e:
        await message.answer(f"❌ Error: {e}")

@dp.message(commands=["signal"])
async def cmd_signal(message: types.Message):
    parts = message.text.split()
    symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
    symbol = normalize_symbol(symbol)
    try:
        signal = ta.rsi_ma_signal(symbol)
        text = f"🔍 *{signal['symbol']} Signal*\n"
        text += f"Price: ${signal['price']}\n"
        text += f"RSI: {signal['rsi']}\n"
        text += f"MA{config.MA_SHORT}: {signal['ma_short']}\n"
        text += f"MA{config.MA_LONG}: {signal['ma_long']}\n"
        text += f"Signal: *{signal['signal']}*"
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Error: {e}")

@dp.message(commands=["balance"])
async def cmd_balance(message: types.Message):
    try:
        summary = portfolio.get_balance_summary()
        text = f"💼 *Portfolio*\nTotal USD: ${summary['total_usd']:,.2f}\n\nAssets:\n"
        for asset in summary['assets'][:10]:
            text += f"• {asset['asset']}: {asset['amount']:.4f} (${asset['value_usd']:,.2f})\n"
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Error: {e}")

@dp.message(commands=["alert_price"])
async def cmd_alert_price(message: types.Message):
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Usage: /alert_price BTCUSDT 70000")
        return
    symbol = normalize_symbol(parts[1])
    try:
        price = float(parts[2])
        alert_manager.set_price_alert(message.from_user.id, symbol, price)
        await message.answer(f"✅ Alert set: {symbol} at ${price}")
    except:
        await message.answer("❌ Invalid price")

@dp.message(commands=["alert_rsi"])
async def cmd_alert_rsi(message: types.Message):
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Usage: /alert_rsi BTCUSDT overbought (or oversold)")
        return
    symbol = normalize_symbol(parts[1])
    condition = parts[2].lower()
    if condition not in ["overbought", "oversold"]:
        await message.answer("Condition must be 'overbought' or 'oversold'")
        return
    alert_manager.set_rsi_alert(message.from_user.id, symbol, condition)
    await message.answer(f"✅ RSI alert set: {symbol} on {condition}")

@dp.message(commands=["my_alerts"])
async def cmd_my_alerts(message: types.Message):
    alerts = alert_manager.get_alerts(message.from_user.id)
    text = "🔔 *Your Alerts*\n"
    text += f"Price alerts: {alerts['price']}\n"
    text += f"RSI alerts: {alerts['rsi']}"
    await message.answer(text, parse_mode="Markdown")

@dp.message(commands=["buy"])
async def cmd_buy(message: types.Message, state: FSMContext):
    keyboard = types.InlineKeyboardMarkup(row_width=4)
    buttons = [
        types.InlineKeyboardButton(text="$10", callback_data="buy_10"),
        types.InlineKeyboardButton(text="$25", callback_data="buy_25"),
        types.InlineKeyboardButton(text="$50", callback_data="buy_50"),
        types.InlineKeyboardButton(text="$100", callback_data="buy_100"),
        types.InlineKeyboardButton(text="✏️ Custom", callback_data="buy_custom"),
    ]
    keyboard.add(*buttons)
    await message.answer("💸 Choose amount to BUY BTC:", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def process_buy_amount(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if callback.data == "buy_custom":
        await callback.message.answer("Please type the amount in USD (e.g., 37):")
        await state.set_state(AmountInput.waiting_for_custom_amount)
        await callback.answer()
        return
    usd = int(callback.data.split("_")[1])
    await callback.answer()
    signal = ta.rsi_ma_signal()
    if signal['signal'] == "HOLD":
        await callback.message.answer("⚠️ No strong signal currently. Use /forcebuy to override (not implemented).")
        return
    await trading_bot.confirm_trade_flow(user_id, signal, usd)

@dp.message(AmountInput.waiting_for_custom_amount)
async def custom_amount_received(message: types.Message, state: FSMContext):
    try:
        usd = float(message.text)
        if usd > config.MAX_TRADE_SIZE_USD:
            await message.answer(f"❌ Max trade size is ${config.MAX_TRADE_SIZE_USD}")
            await state.clear()
            return
        signal = ta.rsi_ma_signal()
        await trading_bot.confirm_trade_flow(message.from_user.id, signal, usd)
        await state.clear()
    except:
        await message.answer("❌ Invalid amount. Please enter a number.")
        await state.clear()

@dp.callback_query(lambda c: c.data.startswith("confirm_"))
async def confirm_trade(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    if user_id != callback.from_user.id:
        await callback.answer("Not your trade", show_alert=True)
        return
    pending = trading_bot.pending_trades.get(user_id)
    if not pending:
        await callback.answer("No pending trade", show_alert=True)
        return
    pending["timeout_task"].cancel()
    result = await trading_bot.execute_trade(
        user_id,
        pending["signal"]["symbol"],
        pending["signal"]["signal"].lower(),
        pending["usd_amount"]
    )
    await callback.message.edit_text(f"✅ Trade confirmed and executed.\nResult: {result}")
    del trading_bot.pending_trades[user_id]

@dp.callback_query(lambda c: c.data.startswith("cancel_"))
async def cancel_trade(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    await trading_bot.cancel_pending_trade(user_id)
    await callback.message.edit_text("❌ Trade cancelled by user.")

async def main():
    register_admin_handlers(dp)
    start_scheduler()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
