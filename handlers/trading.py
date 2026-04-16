from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import binance_client as bc
from config import Config
import numpy as np
import logging

logger = logging.getLogger(__name__)

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    ag = np.mean(gains[:period])
    al = np.mean(losses[:period])
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    return 100 - (100 / (1 + ag / al))

def calculate_ma(closes, period):
    if len(closes) < period:
        return closes[-1] if closes else 0
    return float(np.mean(closes[-period:]))

def get_rsi_ma_signal(symbol):
    try:
        klines = bc.get_klines(symbol, "1h", 100)
        closes = [float(k[4]) for k in klines]
        rsi = calculate_rsi(closes, Config.RSI_PERIOD)
        ma_fast = calculate_ma(closes, Config.MA_FAST)
        ma_slow = calculate_ma(closes, Config.MA_SLOW)
        current = closes[-1]
        signal = "NEUTRAL"
        reasons = []
        if rsi < Config.RSI_OVERSOLD:
            reasons.append(f"RSI={rsi:.1f} (գերծախված/oversold)")
            if ma_fast > ma_slow:
                signal = "BUY"
                reasons.append(f"MA{Config.MA_FAST}>{Config.MA_SLOW} (բուllish)")
        elif rsi > Config.RSI_OVERBOUGHT:
            reasons.append(f"RSI={rsi:.1f} (գերգնված/overbought)")
            if ma_fast < ma_slow:
                signal = "SELL"
                reasons.append(f"MA{Config.MA_FAST}<{Config.MA_SLOW} (bearish)")
        return {
            "signal": signal, "rsi": rsi, "ma_fast": ma_fast,
            "ma_slow": ma_slow, "price": current,
            "reason": ", ".join(reasons) if reasons else "Պայմանները չեն բավարարվել"
        }
    except Exception as e:
        return {"signal": "ERROR", "error": str(e), "rsi": 0, "price": 0, "reason": str(e)}


class TradingHandler:

    async def handle(self, query, context, data):
        action = data.split("_", 1)[1]

        if action == "start":
            context.bot_data['trading_active'] = True
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("⏹ Կանգնեցնել", callback_data="trade_stop"),
                InlineKeyboardButton("🔙 Հետ", callback_data="menu_trading")
            ]])
            await query.edit_message_text(
                "✅ *Ավտո Թրեյդինգը Սկսվեց!*\n\n━━━━━━━━━━━━━━━━━━\nRSI+MA ռազմավարությունն ակտիվ է։\nԱզդանշան հայտնվելիս բոտը կհարցնի հաստատում։",
                reply_markup=kb, parse_mode='Markdown'
            )

        elif action == "stop":
            context.bot_data['trading_active'] = False
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️ Սկսել", callback_data="trade_start"),
                InlineKeyboardButton("🔙 Հետ", callback_data="menu_trading")
            ]])
            await query.edit_message_text(
                "⏹ *Ավտո Թреյдինגը Կանգնեցվեց։*",
                reply_markup=kb, parse_mode='Markdown'
            )

        elif action == "rsi":
            await self._show_rsi(query, context)

        elif action == "info":
            await self._show_info(query, context)

        elif action.startswith("buy_") or action.startswith("sell_"):
            parts = action.split("_", 1)
            direction = parts[0].upper()
            symbol = parts[1]
            context.user_data['pending_trade'] = {'direction': direction, 'symbol': symbol}
            await self._amount_selector(query, context, direction, symbol)

    async def _show_rsi(self, query, context):
        symbol = context.user_data.get('trade_symbol', Config.DEFAULT_SYMBOL)
        try:
            sig = get_rsi_ma_signal(symbol)
            e_map = {"BUY": "🟢", "SELL": "🔴", "NEUTRAL": "⚪", "ERROR": "❌"}
            e = e_map.get(sig['signal'], "⚪")
            sig_hy = {"BUY": "ԳՆԵԼ", "SELL": "ՎԱՃԱՌԵԼ", "NEUTRAL": "ՉԵԶՈՔ", "ERROR": "ՍԽԱԼ"}.get(sig['signal'], "")
            text = (
                f"🤖 *RSI+MA Ռազմավارություն — {symbol}*\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 RSI՝ `{sig.get('rsi', 0):.2f}`\n"
                f"📈 MA{Config.MA_FAST}՝ `{sig.get('ma_fast', 0):.4f}`\n"
                f"📉 MA{Config.MA_SLOW}՝ `{sig.get('ma_slow', 0):.4f}`\n"
                f"💰 Գին՝ `${sig.get('price', 0):.4f}`\n\n"
                f"{e} *Ազդանশань՝ {sig_hy}*\n"
                f"📝 {sig.get('reason', '')}\n\n"
                f"Ավto թреյдинг՝ {'🟢 Ակtiv' if context.bot_data.get('trading_active') else '🔴 Կangnac'}"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🟢 ԳՆԵԼ (BUY)", callback_data=f"trade_buy_{symbol}"),
                 InlineKeyboardButton("🔴 ՎԱՃԱՌEL (SELL)", callback_data=f"trade_sell_{symbol}")],
                [InlineKeyboardButton("🔄 Թarmacel", callback_data="trade_rsi"),
                 InlineKeyboardButton("🔙 Հetq", callback_data="menu_trading")]
            ])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as ex:
            await query.edit_message_text(f"❌ Սխал՝ {ex}")

    async def _amount_selector(self, query, context, direction, symbol):
        try:
            price = bc.get_price(symbol)
        except:
            price = 0
        e = "🟢" if direction == "BUY" else "🔴"
        action_hy = "ԳՆԵԼ" if direction == "BUY" else "ՎԱՃԱՌЕЛ"
        text = (
            f"{e} *{action_hy} — {symbol}*\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Ընthanic գин՝ `${price:,.4f}`\n\n"
            f"💵 Yntreq gumarы USD-ov՝"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("$10", callback_data=f"confirm_trade_{direction}_{symbol}_10"),
             InlineKeyboardButton("$25", callback_data=f"confirm_trade_{direction}_{symbol}_25"),
             InlineKeyboardButton("$50", callback_data=f"confirm_trade_{direction}_{symbol}_50"),
             InlineKeyboardButton("$100", callback_data=f"confirm_trade_{direction}_{symbol}_100")],
            [InlineKeyboardButton("✏️ Ayl Gumar", callback_data="custom_amount")],
            [InlineKeyboardButton("❌ Chegharknel", callback_data="menu_trading")]
        ])
        await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')

    async def confirm_trade(self, query, context, data):
        parts = data.split("_")
        if len(parts) >= 5:
            direction = parts[2]
            symbol = parts[3]
            amount = float(parts[4])
            context.user_data['pending_trade'] = {'direction': direction, 'symbol': symbol}
            await self._show_confirm_query(query, direction, symbol, amount)

    async def _show_confirm_query(self, query, direction, symbol, amount_usd):
        try:
            price = bc.get_price(symbol)
            qty = amount_usd / price
            e = "🟢" if direction == "BUY" else "🔴"
            action_hy = "ԳՆԵԼ" if direction == "BUY" else "ՎԱՃԱՌEL"
            text = (
                f"⚠️ *Հաստател Gorcarqy*\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{e} *{action_hy}* `{symbol}`\n\n"
                f"💵 Gumar՝ `${amount_usd}`\n"
                f"💰 Gin՝ `${price:,.4f}`\n"
                f"📦 Qty՝ `{qty:.6f}`\n\n"
                f"*Hastatel?*"
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"✅ Հաստатem {e}", callback_data=f"execute_trade_{direction}_{symbol}_{amount_usd}"),
                InlineKeyboardButton("❌ Chegharknel", callback_data="menu_trading")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as ex:
            await query.edit_message_text(f"❌ Sxal՝ {ex}")

    async def execute_trade(self, query, context, data):
        parts = data.split("_")
        if len(parts) >= 5:
            await self._do_trade(query, parts[2], parts[3], float(parts[4]))

    async def _do_trade(self, query, direction, symbol, amount_usd):
        try:
            if amount_usd > Config.MAX_TRADE_SIZE_USD:
                await query.edit_message_text(
                    f"❌ Gumarы `${amount_usd}` gereazancum e sahmanadrumy (`${Config.MAX_TRADE_SIZE_USD}`).",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Hetq", callback_data="menu_trading")]])
                )
                return
            price = bc.get_price(symbol)
            qty = round(amount_usd / price, 5)
            await query.edit_message_text(f"⏳ Kargatvum e {direction} {symbol}...")
            result = bc.place_spot_order(symbol, direction, qty)
            e = "🟢" if direction == "BUY" else "🔴"
            action_hy = "GNVEL" if direction == "BUY" else "VACHAREL"
            text = (
                f"✅ *Gorcarqy Kargatvec!*\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{e} {action_hy} `{symbol}`\n"
                f"📦 Qty՝ `{qty:.6f}`\n"
                f"💰 Gin՝ `${price:,.4f}`\n"
                f"💵 Gumar՝ `${amount_usd}`\n"
                f"🆔 Order ID՝ `{result.get('orderId', 'N/A')}`"
            )
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Hetq", callback_data="menu_trading")]]), parse_mode='Markdown')
        except Exception as ex:
            await query.edit_message_text(f"❌ Gorcarqy chi kargatvel՝ {ex}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Hetq", callback_data="menu_trading")]]))

    async def show_trade_confirm(self, update: Update, context, amount_usd):
        pending = context.user_data.get('pending_trade', {})
        direction = pending.get('direction', 'BUY')
        symbol = pending.get('symbol', Config.DEFAULT_SYMBOL)
        try:
            price = bc.get_price(symbol)
            qty = amount_usd / price
            e = "🟢" if direction == "BUY" else "🔴"
            action_hy = "ԳՆEL" if direction == "BUY" else "VACHARЕЛ"
            text = (
                f"⚠️ *Hastatел Gorcarqy*\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{e} *{action_hy}* `{symbol}`\n\n"
                f"💵 Gumar՝ `${amount_usd}`\n"
                f"💰 Gin՝ `${price:,.4f}`\n"
                f"📦 Qty՝ `{qty:.6f}`"
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"✅ Hastatem {e}", callback_data=f"execute_trade_{direction}_{symbol}_{amount_usd}"),
                InlineKeyboardButton("❌ Chegharknel", callback_data="menu_trading")
            ]])
            await update.message.reply_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as ex:
            await update.message.reply_text(f"❌ Sxal՝ {ex}")

    async def _show_info(self, query, context):
        active = context.bot_data.get('trading_active', False)
        text = (
            f"📋 *Ռazmavarутyan Masin*\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🤖 Avto threjding՝ {'🟢 Aktiv' if active else '🔴 Kangnac'}\n"
            f"🛡 Kardalov-Miayн Rejim՝ {'🟡 Miacvac' if Config.READ_ONLY else '🟢 Anjatвac'}\n"
            f"📊 Razmavarутyan՝ RSI+MA\n"
            f"📈 RSI period՝ `{Config.RSI_PERIOD}`\n"
            f"📉 MA periods՝ `{Config.MA_FAST}/{Config.MA_SLOW}`\n"
            f"💰 Max. gorcarq՝ `${Config.MAX_TRADE_SIZE_USD}`\n"
            f"🛑 Orakan sahman՝ `${Config.DAILY_LOSS_LIMIT_USD}`"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Hetq", callback_data="menu_trading")]]), parse_mode='Markdown')
