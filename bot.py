# =========================================
# BINANCE AUTO TRADING TELEGRAM BOT (PRO)
# =========================================

import os
import asyncio
import logging
from datetime import datetime
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

from binance.client import Client

# ========= CONFIG =========
TELEGRAM_TOKEN = "PUT_YOUR_TELEGRAM_TOKEN"
BINANCE_API_KEY = "PUT_YOUR_API_KEY"
BINANCE_SECRET = "PUT_YOUR_SECRET"

TRADE_AMOUNT = 20  # USDT per trade

TOP_COINS = ["BTC", "ETH", "BNB", "SOL", "XRP"]

# ========= INIT =========
client = Client(BINANCE_API_KEY, BINANCE_SECRET)

USER_DATA = defaultdict(lambda: {"portfolio": {}})

# ========= PRICE =========
def get_price(symbol):
    ticker = client.get_symbol_ticker(symbol=symbol + "USDT")
    return float(ticker["price"])

# ========= TA (simple RSI) =========
def get_rsi(prices, period=14):
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(-diff)

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period if losses else 1

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_signal(symbol):
    klines = client.get_klines(symbol=symbol + "USDT", interval="1h", limit=50)
    closes = [float(k[4]) for k in klines]

    rsi = get_rsi(closes)

    if rsi < 30:
        return "BUY", rsi
    elif rsi > 70:
        return "SELL", rsi
    return "HOLD", rsi

# ========= TRADE =========
def place_order(symbol, side):
    price = get_price(symbol)
    qty = TRADE_AMOUNT / price

    if side == "BUY":
        order = client.order_market_buy(symbol=symbol + "USDT", quoteOrderQty=TRADE_AMOUNT)
    else:
        order = client.order_market_sell(symbol=symbol + "USDT", quantity=round(qty, 6))

    return price, qty

# ========= UI =========
def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Auto Trade", callback_data="auto")],
        [InlineKeyboardButton("📊 Scan Market", callback_data="scan")]
    ])

# ========= COMMANDS =========
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 PRO Trading Bot", reply_markup=menu())

# ========= CALLBACK =========
async def buttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "scan":
        text = "📊 Signals:\n\n"
        for coin in TOP_COINS:
            signal, rsi = get_signal(coin)
            text += f"{coin}: {signal} (RSI {round(rsi,1)})\n"

        await query.edit_message_text(text, reply_markup=menu())

    elif query.data == "auto":
        for coin in TOP_COINS:
            signal, rsi = get_signal(coin)

            if signal in ["BUY", "SELL"]:
                price, qty = place_order(coin, signal)

                await query.message.reply_text(
                    f"✅ {signal} {coin}\nPrice: {price}\nQty: {qty:.5f}"
                )

        await query.message.reply_text("🤖 Auto trade finished", reply_markup=menu())

# ========= MAIN =========
async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))

    print("🚀 BOT RUNNING...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
