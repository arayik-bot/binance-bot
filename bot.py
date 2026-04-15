import logging
import os
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from config import Config
from handlers.market import MarketHandler
from handlers.portfolio import PortfolioHandler
from handlers.trading import TradingHandler
from handlers.alerts import AlertHandler
from handlers.analysis import AnalysisHandler
from handlers.admin import AdminHandler

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return 'Բոտը աշխատում է! ✅', 200

@flask_app.route('/health')
def health():
    return 'OK', 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)


def is_authorized(user_id: int) -> bool:
    return user_id in Config.ALLOWED_USERS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Դուք մուտք չունեք։")
        return
    name = update.effective_user.first_name or "Օգտատեր"
    keyboard = [
        [InlineKeyboardButton("📊 Շուկա", callback_data="menu_market"),
         InlineKeyboardButton("💼 Պորտֆոլիո", callback_data="menu_portfolio")],
        [InlineKeyboardButton("🤖 Ավտո Թրեյդինգ", callback_data="menu_trading"),
         InlineKeyboardButton("🔔 Ծանուցումներ", callback_data="menu_alerts")],
        [InlineKeyboardButton("📈 Անալիզ", callback_data="menu_analysis"),
         InlineKeyboardButton("🛠 Կառավարում", callback_data="menu_admin")],
    ]
    await update.message.reply_text(
        f"👋 Բարի գալուստ, *{name}*\!\n\n"
        f"🚀 *Binance Trading Bot*\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 Ընտրեք բաժինը՝",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='MarkdownV2'
    )


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_authorized(query.from_user.id):
        await query.edit_message_text("❌ Դուք մուտք չունեք։")
        return
    data = query.data

    if data == "menu_market":
        kb = [
            [InlineKeyboardButton("💰 Գին", callback_data="market_price"),
             InlineKeyboardButton("📊 Վիճակագրություն 24ժ", callback_data="market_stats")],
            [InlineKeyboardButton("📖 Օրդեր Բուք", callback_data="market_orderbook"),
             InlineKeyboardButton("🕯 Մոմիկներ", callback_data="market_candles")],
            [InlineKeyboardButton("🏆 Լավագույն Աճ", callback_data="market_gainers"),
             InlineKeyboardButton("📉 Լավագույն Անկում", callback_data="market_losers")],
            [InlineKeyboardButton("💸 Ֆինանսավորման տոկոս", callback_data="market_funding"),
             InlineKeyboardButton("🔙 Հետ", callback_data="menu_main")]
        ]
        await query.edit_message_text(
            "📊 *Շուկայական Տվյալներ*\n\n━━━━━━━━━━━━━━━━━━\n📌 Ընտրեք՝",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
        )

    elif data == "menu_portfolio":
        kb = [
            [InlineKeyboardButton("💰 Սփոթ Բալանս", callback_data="portfolio_spot"),
             InlineKeyboardButton("📊 Ֆյուչերս Բալանս", callback_data="portfolio_futures")],
            [InlineKeyboardButton("📋 Բաց Օրդերներ", callback_data="portfolio_orders"),
             InlineKeyboardButton("📜 Գործարքների Պատմություն", callback_data="portfolio_history")],
            [InlineKeyboardButton("💹 Շահույթ/Վնաս (PnL)", callback_data="portfolio_pnl"),
             InlineKeyboardButton("🥧 Ակտիվների Բաշխում", callback_data="portfolio_allocation")],
            [InlineKeyboardButton("🔙 Հետ", callback_data="menu_main")]
        ]
        await query.edit_message_text(
            "💼 *Պորտֆոլիո*\n\n━━━━━━━━━━━━━━━━━━\n📌 Ընտրեք՝",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
        )

    elif data == "menu_trading":
        status = "🟢 Ակտիվ" if context.bot_data.get('trading_active', False) else "🔴 Կանգնած"
        kb = [
            [InlineKeyboardButton("▶️ Սկսել Թրեյդինգ", callback_data="trade_start"),
             InlineKeyboardButton("⏹ Կանգնեցնել", callback_data="trade_stop")],
            [InlineKeyboardButton("🤖 RSI+MA Ռազմավարություն", callback_data="trade_rsi"),
             InlineKeyboardButton("📋 Տեղեկություն", callback_data="trade_info")],
            [InlineKeyboardButton("🔙 Հետ", callback_data="menu_main")]
        ]
        await query.edit_message_text(
            f"🤖 *Ավտո Թրեյդինգ*\n\n━━━━━━━━━━━━━━━━━━\n📡 Կարգավիճակ՝ {status}\n\n📌 Ընտրեք՝",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
        )

    elif data == "menu_alerts":
        kb = [
            [InlineKeyboardButton("🔔 Ստեղծել Ծանուցում", callback_data="alert_price"),
             InlineKeyboardButton("📜 Իմ Ծանուցումները", callback_data="alert_list")],
            [InlineKeyboardButton("❌ Ջնջել Բոլորը", callback_data="alert_clear"),
             InlineKeyboardButton("🔙 Հետ", callback_data="menu_main")]
        ]
        await query.edit_message_text(
            "🔔 *Ծանուցումներ*\n\n━━━━━━━━━━━━━━━━━━\n📌 Ընտրեք՝",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
        )

    elif data == "menu_analysis":
        kb = [
            [InlineKeyboardButton("📊 RSI", callback_data="analysis_rsi"),
             InlineKeyboardButton("📈 MACD", callback_data="analysis_macd")],
            [InlineKeyboardButton("📉 Bollinger Bands", callback_data="analysis_bb"),
             InlineKeyboardButton("🎯 Աջակցություն/Դիմադրություն", callback_data="analysis_sr")],
            [InlineKeyboardButton("📡 Ազդանշաններ", callback_data="analysis_signals"),
             InlineKeyboardButton("📊 Գծապատկեր", callback_data="analysis_chart")],
            [InlineKeyboardButton("🔙 Հետ", callback_data="menu_main")]
        ]
        await query.edit_message_text(
            "📈 *Տեխնիկական Անալիզ*\n\n━━━━━━━━━━━━━━━━━━\n📌 Ընտրեք՝",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
        )

    elif data == "menu_admin":
        kb = [
            [InlineKeyboardButton("📜 Լոգեր", callback_data="admin_logs"),
             InlineKeyboardButton("🔍 Բոտի Կարգավիճակ", callback_data="admin_status")],
            [InlineKeyboardButton("🛡 Կարդալ-Միայն Ռեժիմ", callback_data="admin_readonly"),
             InlineKeyboardButton("📊 Ռիսկի Սահմանաչափ", callback_data="admin_limit")],
            [InlineKeyboardButton("🔙 Հետ", callback_data="menu_main")]
        ]
        await query.edit_message_text(
            "🛠 *Կառավարում*\n\n━━━━━━━━━━━━━━━━━━\n📌 Ընտրեք՝",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
        )

    elif data == "menu_main":
        kb = [
            [InlineKeyboardButton("📊 Շուկա", callback_data="menu_market"),
             InlineKeyboardButton("💼 Պորտֆոլիո", callback_data="menu_portfolio")],
            [InlineKeyboardButton("🤖 Ավտո Թրեյդինգ", callback_data="menu_trading"),
             InlineKeyboardButton("🔔 Ծանուցումներ", callback_data="menu_alerts")],
            [InlineKeyboardButton("📈 Անալիզ", callback_data="menu_analysis"),
             InlineKeyboardButton("🛠 Կառավարում", callback_data="menu_admin")]
        ]
        await query.edit_message_text(
            "🚀 *Binance Trading Bot*\n\n━━━━━━━━━━━━━━━━━━\n📌 Ընտրեք բաժինը՝",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
        )

    elif data.startswith("market_"):
        await MarketHandler().handle(query, context, data)
    elif data.startswith("portfolio_"):
        await PortfolioHandler().handle(query, context, data)
    elif data.startswith("trade_"):
        await TradingHandler().handle(query, context, data)
    elif data.startswith("execute_trade_"):
        await TradingHandler().execute_trade(query, context, data)
    elif data.startswith("confirm_trade_"):
        await TradingHandler().confirm_trade(query, context, data)
    elif data.startswith("alert_"):
        await AlertHandler().handle(query, context, data)
    elif data.startswith("analysis_"):
        await AnalysisHandler().handle(query, context, data)
    elif data.startswith("admin_"):
        await AdminHandler().handle(query, context, data)
    elif data == "custom_amount":
        pending = context.user_data.get('pending_trade', {})
        if pending:
            context.user_data['waiting_custom_amount'] = True
            await query.edit_message_text(
                f"✏️ *Մուտքագրեք գումարը USD-ով*\n\n"
                f"Օրինակ՝ `37`\n\n"
                f"🪙 Մոնետ՝ {pending.get('symbol','BTCUSDT')} | {pending.get('direction','BUY')}",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ Սխալ։ Գրեք /start")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    text = update.message.text.strip()
    if context.user_data.get('waiting_custom_amount'):
        try:
            amount = float(text.replace('$', '').replace(',', ''))
            context.user_data['waiting_custom_amount'] = False
            await TradingHandler().show_trade_confirm(update, context, amount)
        except ValueError:
            await update.message.reply_text("❌ Սխալ։ Մուտքագրեք թիվ, օրինակ՝ `37`", parse_mode='Markdown')
    elif context.user_data.get('waiting_alert_price'):
        await AlertHandler().process_alert_input(update, context, text)


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    if context.args:
        await MarketHandler().get_price(update, context, context.args[0].upper())
    else:
        await update.message.reply_text("Օրինակ՝ `/price BTC`", parse_mode='Markdown')


async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return
    if len(context.args) >= 2:
        try:
            await AlertHandler().set_price_alert(update, context, context.args[0].upper(), float(context.args[1]))
        except ValueError:
            await update.message.reply_text("Օրինակ՝ `/alert BTC 90000`", parse_mode='Markdown')
    else:
        await update.message.reply_text("Օրինակ՝ `/alert BTC 90000`", parse_mode='Markdown')


async def alert_checker(app):
    while True:
        await asyncio.sleep(Config.ALERT_CHECK_INTERVAL)
        alerts = app.bot_data.get('price_alerts', [])
        for alert in alerts:
            if not alert.get('active'):
                continue
            try:
                from binance_client import get_price
                current = get_price(alert['symbol'])
                target = alert['target_price']
                last = alert.get('last_price')
                if last is not None:
                    if (last < target <= current) or (last > target >= current):
                        e = "⬆️" if current >= target else "⬇️"
                        await app.bot.send_message(
                            chat_id=alert['user_id'],
                            text=(
                                f"🔔 *Գնի Ծանուցում!*\n\n"
                                f"{e} `{alert['symbol']}`\n"
                                f"💰 Հասել է՝ `${current:,.4f}`\n"
                                f"🎯 Ձեր թիրախ՝ `${target:,.4f}`"
                            ),
                            parse_mode='Markdown'
                        )
                        alert['active'] = False
                alert['last_price'] = current
            except Exception as ex:
                logger.error(f"Alert error: {ex}")


async def strategy_checker(app):
    while True:
        await asyncio.sleep(Config.STRATEGY_CHECK_INTERVAL)
        if not app.bot_data.get('trading_active', False):
            continue
        try:
            from handlers.trading import get_rsi_ma_signal
            sig = get_rsi_ma_signal(Config.DEFAULT_SYMBOL)
            if sig['signal'] not in ['BUY', 'SELL']:
                continue
            d = sig['signal']
            d_hy = "ԳՆԵԼ" if d == "BUY" else "ՎԱՃԱՌԵԼ"
            e = "🟢" if d == "BUY" else "🔴"
            sym = Config.DEFAULT_SYMBOL
            kb = [
                [InlineKeyboardButton(f"$10 {e}", callback_data=f"confirm_trade_{d}_{sym}_10"),
                 InlineKeyboardButton(f"$25 {e}", callback_data=f"confirm_trade_{d}_{sym}_25"),
                 InlineKeyboardButton(f"$50 {e}", callback_data=f"confirm_trade_{d}_{sym}_50"),
                 InlineKeyboardButton(f"$100 {e}", callback_data=f"confirm_trade_{d}_{sym}_100")],
                [InlineKeyboardButton("✏️ Այլ Գումար", callback_data="custom_amount"),
                 InlineKeyboardButton("❌ Բաց Թողնել", callback_data="menu_trading")]
            ]
            for uid in Config.ALLOWED_USERS:
                try:
                    await app.bot.send_message(
                        chat_id=uid,
                        text=(
                            f"🤖 *Թրեյդինգ Ազդանշան!*\n\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"{e} *{d_hy}* `{sym}`\n"
                            f"💰 Գին՝ `${sig['price']:,.4f}`\n"
                            f"📊 RSI՝ `{sig['rsi']:.1f}`\n"
                            f"📝 {sig['reason']}\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"💵 Ընտրեք գումարը՝"
                        ),
                        reply_markup=InlineKeyboardMarkup(kb),
                        parse_mode='Markdown'
                    )
                except Exception as ex:
                    logger.error(f"Send error: {ex}")
        except Exception as ex:
            logger.error(f"Strategy error: {ex}")


async def run_bot():
    Thread(target=run_flask, daemon=True).start()
    logger.info("✅ Flask started!")

    app = ApplicationBuilder().token(Config.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CommandHandler("alert", alert_command))
    app.add_handler(CallbackQueryHandler(menu_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    logger.info("✅ Bot started!")

    asyncio.create_task(alert_checker(app))
    asyncio.create_task(strategy_checker(app))

    await asyncio.Event().wait()


if __name__ == '__main__':
    asyncio.run(run_bot())
