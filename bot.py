import os
import asyncio
import ccxt
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from aiohttp import web

# ===== ENV VARIABLES =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
ALLOWED_USERS = os.getenv("ALLOWED_USERS", "")
PORT = int(os.getenv("PORT", 10000))

try:
    CHAT_ID = int(ALLOWED_USERS.split(",")[0].strip())
except:
    CHAT_ID = 0

DEFAULT_TRADE_AMOUNT = 25
TIMEOUT_SECONDS = 30

# ===== BINANCE TESTNET =====
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET_KEY,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})
exchange.set_sandbox_mode(True)

pending_trades = {}
bot_running = False
current_symbol = 'BTC/USDT'

# ===== ԳԼԽԱՎՈՐ ՄԵՆՅՈՒ =====
def get_main_menu():
    keyboard = [
        [KeyboardButton("📊 Շուկայի Տվյալներ"), KeyboardButton("💼 Պորտֆոլիո")],
        [KeyboardButton("🤖 Ավտո Առևտուր"), KeyboardButton("🔔 Ծանուցումներ")],
        [KeyboardButton("📈 Վերլուծություն"), KeyboardButton("⚙️ Կառավարում")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ===== RSI + CHART =====
def get_rsi_and_chart(symbol='BTC/USDT', timeframe='5m', period=14):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1]

    df = df.tail(20)
    fig, ax = plt.subplots(figsize=(6, 3), facecolor='#131722')
    ax.set_facecolor('#131722')

    for i in range(len(df)):
        color = '#089981' if df['close'].iloc[i] >= df['open'].iloc[i] else '#F23645'
        ax.plot([i, i], [df['low'].iloc[i], df['high'].iloc[i]], color=color, linewidth=1)
        ax.plot([i, i], [df['open'].iloc[i], df['close'].iloc[i]], color=color, linewidth=4)

    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values(): spine.set_visible(False)
    plt.tight_layout(pad=0.1)

    buf = BytesIO()
    plt.savefig(buf, format='png', facecolor='#131722', dpi=100)
    buf.seek(0)
    plt.close()

    return current_rsi, df['close'].iloc[-1], buf

# ===== SIGNAL ՍՏՈՒԳԵԼ =====
async def check_signal(context: ContextTypes.DEFAULT_TYPE):
    global CHAT_ID
    if CHAT_ID == 0 or not bot_running: return

    try:
        rsi, price, chart = get_rsi_and_chart(current_symbol)

        action = None
        if rsi < 30:
            action, signal_text, emoji = 'buy', "BUY ✅", "📈"
        elif rsi > 70:
            action, signal_text, emoji = 'sell', "SELL 🔴", "📉"
        else:
            return

        rsi_bar = "▓" * int(rsi/10) + "░" * (10 - int(rsi/10))
        rsi_status = "OVERSOLD" if rsi < 30 else "OVERBOUGHT"

        text = f"""{current_symbol} ${price:,.0f} {emoji}
━━━━━━━━━━━━━━━━━━━━━━
RSI: {rsi:.1f} {rsi_bar} {rsi_status}
Signal: {signal_text}

Ընտրիր գումարը․"""

        keyboard = [
            [InlineKeyboardButton("$10", callback_data=f"trade_{action}_10"),
             InlineKeyboardButton("$25", callback_data=f"trade_{action}_25")],
            [InlineKeyboardButton("$50", callback_data=f"trade_{action}_50"),
             InlineKeyboardButton("$100", callback_data=f"trade_{action}_100")],
            [InlineKeyboardButton("Custom $", callback_data=f"custom_{action}"),
             InlineKeyboardButton("Cancel", callback_data="cancel")]
        ]

        msg = await context.bot.send_photo(
            chat_id=CHAT_ID,
            photo=chart,
            caption=text + f"\n⏱ {TIMEOUT_SECONDS}s մինչև ավտոմատ ${DEFAULT_TRADE_AMOUNT}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        pending_trades[CHAT_ID] = {'action': action, 'symbol': current_symbol, 'msg_id': msg.message_id, 'price': price}

        context.job_queue.run_once(
            execute_timeout_trade, TIMEOUT_SECONDS,
            data={'chat_id': CHAT_ID, 'action': action, 'amount': DEFAULT_TRADE_AMOUNT},
            name=f"timeout_{msg.message_id}"
        )
    except Exception as e:
        print(f"Signal Error: {e}")

# ===== TIMEOUT TRADE =====
async def execute_timeout_trade(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    if CHAT_ID not in pending_trades: return

    action = job.data['action']
    amount = job.data['amount']
    price = pending_trades[CHAT_ID]['price']
    symbol = pending_trades[CHAT_ID]['symbol']

    try:
        if action == 'buy':
            order = exchange.create_market_buy_order(symbol, amount / price)
        else:
            order = exchange.create_market_sell_order(symbol, amount / price)
        await context.bot.send_message(CHAT_ID, f"⏱ Timeout! Ավտոմատ {action.upper()} ${amount}\nOrder ID: {order['id']}", reply_markup=get_main_menu())
    except Exception as e:
        await context.bot.send_message(CHAT_ID, f"❌ Error: {str(e)}", reply_markup=get_main_menu())

    del pending_trades[CHAT_ID]

# ===== INLINE ԿՈՃԱԿՆԵՐ =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    for job in context.job_queue.get_jobs_by_name(f"timeout_{query.message.message_id}"):
        job.schedule_removal()

    if query.data == "cancel":
        await query.edit_message_caption(caption="❌ Trade-ը չեղարկվեց")
        if CHAT_ID in pending_trades: del pending_trades[CHAT_ID]
        return

    if query.data.startswith("custom_"):
        pending_trades[CHAT_ID]['waiting_custom'] = query.data.split("_")[1]
        await query.edit_message_caption(caption="Գրիր գումարը, օրինակ՝ 37")
        return

    if query.data.startswith("trade_"):
        _, action, amount = query.data.split("_")
        amount = float(amount)
        price = pending_trades[CHAT_ID]['price']
        symbol = pending_trades[CHAT_ID]['symbol']

        try:
            if action == 'buy':
                order = exchange.create_market_buy_order(symbol, amount / price)
            else:
                order = exchange.create_market_sell_order(symbol, amount / price)
            await query.edit_message_caption(caption=f"✅ {action.upper()} ${amount}\nOrder ID: {order['id']}")
        except Exception as e:
            await query.edit_message_caption(caption=f"❌ Error: {str(e)}")

        if CHAT_ID in pending_trades: del pending_trades[CHAT_ID]

# ===== ՄԵՆՅՈՒԻ ԿՈՃԱԿՆԵՐ =====
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CHAT_ID, bot_running, current_symbol
    user_id = update.effective_chat.id
    text = update.message.text

    allowed = [int(x.strip()) for x in ALLOWED_USERS.split(",") if x.strip()]
    if user_id not in allowed:
        await update.message.reply_text("⛔ Դու չես կարա օգտագործես էս բոտը")
        return

    CHAT_ID = user_id

    # Եթե սպասում ենք custom գումար
    if CHAT_ID in pending_trades and 'waiting_custom' in pending_trades[CHAT_ID]:
        try:
            amount = float(text)
            if amount <= 0: raise ValueError
        except:
            await update.message.reply_text("Խնդրում եմ թիվ գրի, օրինակ՝ 37", reply_markup=get_main_menu())
            return

        action = pending_trades[CHAT_ID]['waiting_custom']
        price = pending_trades[CHAT_ID]['price']
        symbol = pending_trades[CHAT_ID]['symbol']

        for job in context.job_queue.get_jobs_by_name(f"timeout_{pending_trades[CHAT_ID]['msg_id']}"):
            job.schedule_removal()

        try:
            if action == 'buy':
                order = exchange.create_market_buy_order(symbol, amount / price)
            else:
                order = exchange.create_market_sell_order(symbol, amount / price)
            await update.message.reply_text(f"✅ {action.upper()} ${amount}\nOrder ID: {order['id']}", reply_markup=get_main_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}", reply_markup=get_main_menu())

        del pending_trades[CHAT_ID]
        return

    # ===== ՄԵՆՅՈՒԻ ԲԱԺԻՆՆԵՐ =====
    if text == "📊 Շուկայի Տվյալներ":
        try:
            await context.bot.send_message(chat_id=CHAT_ID, text=f"📊 Generating chart {current_symbol}... ⏳")
            rsi, price, chart = get_rsi_and_chart(current_symbol)
            rsi_bar = "▓" * int(rsi/10) + "░" * (10 - int(rsi/10))
            status = "OVERSOLD 🔴" if rsi < 30 else "OVERBOUGHT 🔴" if rsi > 70 else "NORMAL 🟢"
            msg = f"{current_symbol}\nԳին: ${price:,.2f}\nRSI: {rsi:.1f} {rsi_bar}\nStatus: {status}"
            await context.bot.send_photo(chat_id=CHAT_ID, photo=chart, caption=msg, reply_markup=get_main_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}", reply_markup=get_main_menu())

    elif text == "💼 Պորտֆոլիո":
        try:
            balance = exchange.fetch_balance()
            usdt = balance['USDT']['free'] if 'USDT' in balance else 0
            btc = balance['BTC']['free'] if 'BTC' in balance else 0
            ticker = exchange.fetch_ticker('BTC/USDT')
            total = usdt + btc * ticker['last']
            msg = f"""💼 Պորտֆոլիո (Testnet)
━━━━━━━━━━━━━━━━━━━━━━
USDT: ${usdt:.2f}
BTC: {btc:.6f}

Ընդհանուր: ${total:.2f}"""
            await update.message.reply_text(msg, reply_markup=get_main_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}", reply_markup=get_main_menu())

    elif text == "🤖 Ավտո Առևտուր":
        if bot_running:
            bot_running = False
            for job in context.job_queue.get_jobs_by_name("rsi_check"):
                job.schedule_removal()
            await update.message.reply_text("🛑 Ավտո առևտուրը անջատվեց", reply_markup=get_main_menu())
        else:
            bot_running = True
            context.job_queue.run_repeating(check_signal, interval=300, first=10, name="rsi_check")
            await update.message.reply_text("✅ Ավտո առևտուրը միացավ\n\nԱմեն 5 րոպեն մեկ կստուգեմ RSI:\nSignal լինի՝ կուղարկեմ:", reply_markup=get_main_menu())

    elif text == "🔔 Ծանուցումներ":
        status = "Միացված ✅" if bot_running else "Անջատված ❌"
        msg = f"""🔔 Ծանուցումներ
━━━━━━━━━━━━━━━━━━━━━━
Կարգավիճակ: {status}

Միացնել/անջատելու համար սեղմիր '🤖 Ավտո Առևտուր'"""
        await update.message.reply_text(msg, reply_markup=get_main_menu())

    elif text == "📈 Վերլուծություն":
        try:
            await context.bot.send_message(chat_id=CHAT_ID, text="📈 Վերլուծությունը պատրաստվում է... ⏳")
            rsi, price, chart = get_rsi_and_chart(current_symbol, '1h')
            msg = f"""📈 Վերլուծություն 1H
━━━━━━━━━━━━━━━━━━━━━━
{current_symbol}: ${price:,.2f}
RSI: {rsi:.1f}

Եթե RSI < 30՝ BUY signal 📈
Եթե RSI > 70՝ SELL signal 📉
Հակառակ դեպքում՝ սպասել"""
            await context.bot.send_photo(chat_id=CHAT_ID, photo=chart, caption=msg, reply_markup=get_main_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}", reply_markup=get_main_menu())

    elif text == "⚙️ Կառավարում":
        msg = f"""⚙️ Կարգավորումներ
━━━━━━━━━━━━━━━━━━━━━━
Ընթացիկ զույգ: {current_symbol}
Ավտոմատ գումար: ${DEFAULT_TRADE_AMOUNT}
Timeout: {TIMEOUT_SECONDS} վայրկյան
Ավտո առևտուր: {"Միացված ✅" if bot_running else "Անջատված ❌"}

Փոխելու համար կոդը խմբագրի:"""
        await update.message.reply_text(msg, reply_markup=get_main_menu())

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CHAT_ID
    user_id = update.effective_chat.id

    allowed = [int(x.strip()) for x in ALLOWED_USERS.split(",") if x.strip()]
    if user_id not in allowed:
        await update.message.reply_text("⛔ Դու չես կարա օգտագործես էս բոտը")
        return

    CHAT_ID = user_id
    text = """🚀 Binance Trading Bot

Ընտրիր բաժինը:"""
    await update.message.reply_text(text, reply_markup=get_main_menu())

# ===== FAKE WEB SERVER =====
async def health_check(request):
    return web.Response(text="Bot is running")

async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get('/', health_check)
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

# ===== MAIN =====
async def main():
    await start_web_server()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    print("Bot started...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
