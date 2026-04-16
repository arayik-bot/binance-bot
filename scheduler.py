from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import Config
import binance_client as bc
import logging

logger = logging.getLogger(__name__)


async def check_price_alerts(app):
    alerts = app.bot_data.get('price_alerts', [])
    for alert in alerts:
        if not alert.get('active'):
            continue
        try:
            current = bc.get_price(alert['symbol'])
            target = alert['target_price']
            last = alert.get('last_price', None)
            triggered = False
            if last is not None:
                if last < target <= current:
                    triggered = True
                elif last > target >= current:
                    triggered = True
            if triggered:
                emoji = "⬆️" if current >= target else "⬇️"
                await app.bot.send_message(
                    chat_id=alert['user_id'],
                    text=(
                        f"🔔 *Price Alert!*\n\n"
                        f"{emoji} `{alert['symbol']}`\n"
                        f"Հасел е `${current:,.4f}`\n"
                        f"Ձеr target՝ `${target:,.4f}`"
                    ),
                    parse_mode='Markdown'
                )
                alert['active'] = False
            alert['last_price'] = current
        except Exception as e:
            logger.error(f"Alert error: {e}")


async def check_rsi_strategy(app):
    if not app.bot_data.get('trading_active', False):
        return
    from handlers.trading import get_rsi_ma_signal
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    symbol = Config.DEFAULT_SYMBOL
    try:
        sig = get_rsi_ma_signal(symbol)
        if sig['signal'] not in ['BUY', 'SELL']:
            return
        direction = sig['signal']
        emoji = "🟢" if direction == "BUY" else "🔴"
        text = (
            f"🤖 *Auto Trading Signal!*\n\n"
            f"{emoji} *{direction}* — `{symbol}`\n"
            f"💰 Gin: `${sig['price']:,.4f}`\n"
            f"📊 RSI: `{sig['rsi']:.2f}`\n"
            f"📝 {sig['reason']}\n\n"
            f"Yntreq gumarы:"
        )
        keyboard = [
            [InlineKeyboardButton(f"$10 {emoji}", callback_data=f"confirm_trade_{direction}_{symbol}_10"),
             InlineKeyboardButton(f"$25 {emoji}", callback_data=f"confirm_trade_{direction}_{symbol}_25"),
             InlineKeyboardButton(f"$50 {emoji}", callback_data=f"confirm_trade_{direction}_{symbol}_50"),
             InlineKeyboardButton(f"$100 {emoji}", callback_data=f"confirm_trade_{direction}_{symbol}_100")],
            [InlineKeyboardButton("✏️ Custom", callback_data="custom_amount"),
             InlineKeyboardButton("❌ Skip", callback_data="menu_trading")]
        ]
        for user_id in Config.ALLOWED_USERS:
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Send error to {user_id}: {e}")
    except Exception as e:
        logger.error(f"Strategy error: {e}")


def setup_scheduler(app):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_price_alerts,
        'interval',
        seconds=Config.ALERT_CHECK_INTERVAL,
        args=[app]
    )
    scheduler.add_job(
        check_rsi_strategy,
        'interval',
        seconds=Config.STRATEGY_CHECK_INTERVAL,
        args=[app]
    )
    # Use app's event loop
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    scheduler.start()
    logger.info("✅ Scheduler started!")
