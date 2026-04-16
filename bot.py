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
from alerts import AlertManager
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

@dp.message(lambda message: message.from_user.id in config.ALLOWED_USER_IDS, commands=["price"])
async def cmd_price(message: types.Message):
    symbol = message.text.split()[1] if len(message.text.split()) > 1 else "BTCUSDT"
    price = market.get_price(symbol.upper())
    await message.answer(f"💰 {symbol.upper()}: ${price}")

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
    # Get signal and start confirmation flow
    signal = ta.rsi_ma_signal()
    if signal['signal'] == "HOLD":
        await callback.message.answer("No strong signal currently. Trade anyway? (Use /forcebuy)")
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
