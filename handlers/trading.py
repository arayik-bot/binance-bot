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
            reasons.append(f"RSI={rsi:.1f} (перепродан/oversold)")
            if ma_fast > ma_slow:
                signal = "BUY"
                reasons.append(f"MA{Config.MA_FAST}>{Config.MA_SLOW} (бычий/bullish)")
        elif rsi > Config.RSI_OVERBOUGHT:
            reasons.append(f"RSI={rsi:.1f} (перекуплен/overbought)")
            if ma_fast < ma_slow:
                signal = "SELL"
                reasons.append(f"MA{Config.MA_FAST}<{Config.MA_SLOW} (медвежий/bearish)")
        return {
            "signal": signal, "rsi": rsi, "ma_fast": ma_fast,
            "ma_slow": ma_slow, "price": current,
            "reason": ", ".join(reasons) if reasons else "Условия не выполнены"
        }
    except Exception as e:
        return {"signal": "ERROR", "error": str(e), "rsi": 0, "price": 0, "reason": str(e)}


class TradingHandler:

    async def handle(self, query, context, data):
        action = data.split("_", 1)[1]

        if action == "start":
            context.bot_data['trading_active'] = True
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("⏹ Остановить", callback_data="trade_stop"),
                InlineKeyboardButton("🔙 Назад", callback_data="menu_trading")
            ]])
            await query.edit_message_text(
                "✅ *Авто торговля запущена!*\n\nСтратегия RSI+MA активна.\nКогда появится сигнал — бот спросит подтверждение.",
                reply_markup=kb, parse_mode='Markdown'
            )

        elif action == "stop":
            context.bot_data['trading_active'] = False
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("▶️ Запустить", callback_data="trade_start"),
                InlineKeyboardButton("🔙 Назад", callback_data="menu_trading")
            ]])
            await query.edit_message_text("⏹ *Авто торговля остановлена.*", reply_markup=kb, parse_mode='Markdown')

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
            sig_ru = {"BUY": "КУПИТЬ", "SELL": "ПРОДАТЬ", "NEUTRAL": "НЕЙТРАЛЬНО", "ERROR": "ОШИБКА"}.get(sig['signal'], "")
            text = (
                f"🤖 *Стратегия RSI+MA — {symbol}*\n\n"
                f"📊 RSI (индекс силы): `{sig.get('rsi', 0):.2f}`\n"
                f"📈 MA{Config.MA_FAST} (скользящая): `{sig.get('ma_fast', 0):.4f}`\n"
                f"📉 MA{Config.MA_SLOW} (скользящая): `{sig.get('ma_slow', 0):.4f}`\n"
                f"💰 Цена (Price): `${sig.get('price', 0):.4f}`\n\n"
                f"{e} *Сигнал: {sig_ru}*\n"
                f"📝 {sig.get('reason', '')}\n\n"
                f"Авто торговля: {'🟢 Активна' if context.bot_data.get('trading_active') else '🔴 Остановлена'}"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🟢 КУПИТЬ (BUY)", callback_data=f"trade_buy_{symbol}"),
                 InlineKeyboardButton("🔴 ПРОДАТЬ (SELL)", callback_data=f"trade_sell_{symbol}")],
                [InlineKeyboardButton("🔄 Обновить", callback_data="trade_rsi"),
                 InlineKeyboardButton("🔙 Назад", callback_data="menu_trading")]
            ])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as ex:
            await query.edit_message_text(f"❌ Ошибка: {ex}")

    async def _amount_selector(self, query, context, direction, symbol):
        try:
            price = bc.get_price(symbol)
        except:
            price = 0
        e = "🟢" if direction == "BUY" else "🔴"
        action_ru = "КУПИТЬ" if direction == "BUY" else "ПРОДАТЬ"
        text = (
            f"{e} *{action_ru} ({direction}) — {symbol}*\n\n"
            f"💰 Текущая цена (Price): `${price:,.4f}`\n\n"
            f"Выберите сумму в USD:"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("$10", callback_data=f"confirm_trade_{direction}_{symbol}_10"),
             InlineKeyboardButton("$25", callback_data=f"confirm_trade_{direction}_{symbol}_25"),
             InlineKeyboardButton("$50", callback_data=f"confirm_trade_{direction}_{symbol}_50"),
             InlineKeyboardButton("$100", callback_data=f"confirm_trade_{direction}_{symbol}_100")],
            [InlineKeyboardButton("✏️ Другая сумма", callback_data="custom_amount")],
            [InlineKeyboardButton("❌ Отмена", callback_data="menu_trading")]
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
            action_ru = "КУПИТЬ" if direction == "BUY" else "ПРОДАТЬ"
            text = (
                f"⚠️ *Подтвердите сделку (Trade)*\n\n"
                f"{e} *{action_ru}* `{symbol}`\n\n"
                f"💵 Сумма: `${amount_usd}`\n"
                f"💰 Цена (Price): `${price:,.4f}`\n"
                f"📦 Количество (Qty): `{qty:.6f}`\n\n"
                f"*Подтвердить или отменить?*"
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"✅ Подтверждаю {e}", callback_data=f"execute_trade_{direction}_{symbol}_{amount_usd}"),
                InlineKeyboardButton("❌ Отмена", callback_data="menu_trading")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as ex:
            await query.edit_message_text(f"❌ Ошибка: {ex}")

    async def execute_trade(self, query, context, data):
        parts = data.split("_")
        if len(parts) >= 5:
            await self._do_trade(query, parts[2], parts[3], float(parts[4]))

    async def _do_trade(self, query, direction, symbol, amount_usd):
        try:
            if amount_usd > Config.MAX_TRADE_SIZE_USD:
                await query.edit_message_text(
                    f"❌ Сумма `${amount_usd}` превышает лимит (`${Config.MAX_TRADE_SIZE_USD}`).",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="menu_trading")]])
                )
                return
            price = bc.get_price(symbol)
            qty = round(amount_usd / price, 5)
            await query.edit_message_text(f"⏳ Выполняю {direction} {symbol}...")
            result = bc.place_spot_order(symbol, direction, qty)
            e = "🟢" if direction == "BUY" else "🔴"
            action_ru = "КУПЛЕНО" if direction == "BUY" else "ПРОДАНО"
            text = (
                f"✅ *Сделка выполнена!*\n\n"
                f"{e} {action_ru} `{symbol}`\n"
                f"📦 Кол-во (Qty): `{qty:.6f}`\n"
                f"💰 Цена (Price): `${price:,.4f}`\n"
                f"💵 Сумма: `${amount_usd}`\n"
                f"🆔 Order ID: `{result.get('orderId', 'N/A')}`"
            )
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="menu_trading")]]), parse_mode='Markdown')
        except Exception as ex:
            await query.edit_message_text(f"❌ Сделка не выполнена: {ex}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="menu_trading")]]))

    async def show_trade_confirm(self, update: Update, context, amount_usd):
        pending = context.user_data.get('pending_trade', {})
        direction = pending.get('direction', 'BUY')
        symbol = pending.get('symbol', Config.DEFAULT_SYMBOL)
        try:
            price = bc.get_price(symbol)
            qty = amount_usd / price
            e = "🟢" if direction == "BUY" else "🔴"
            action_ru = "КУПИТЬ" if direction == "BUY" else "ПРОДАТЬ"
            text = (
                f"⚠️ *Подтвердите сделку (Trade)*\n\n"
                f"{e} *{action_ru}* `{symbol}`\n\n"
                f"💵 Сумма: `${amount_usd}`\n"
                f"💰 Цена (Price): `${price:,.4f}`\n"
                f"📦 Кол-во (Qty): `{qty:.6f}`"
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"✅ Подтверждаю {e}", callback_data=f"execute_trade_{direction}_{symbol}_{amount_usd}"),
                InlineKeyboardButton("❌ Отмена", callback_data="menu_trading")
            ]])
            await update.message.reply_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as ex:
            await update.message.reply_text(f"❌ Ошибка: {ex}")

    async def _show_info(self, query, context):
        active = context.bot_data.get('trading_active', False)
        text = (
            f"📋 *О стратегии (Strategy Info)*\n\n"
            f"🤖 Авто торговля: {'🟢 Активна' if active else '🔴 Остановлена'}\n"
            f"🛡 Режим чтения (Read-Only): {'🟡 Вкл' if Config.READ_ONLY else '🟢 Выкл'}\n"
            f"📊 Стратегия (Strategy): RSI+MA\n"
            f"📈 RSI период: `{Config.RSI_PERIOD}`\n"
            f"📉 MA периоды: `{Config.MA_FAST}/{Config.MA_SLOW}`\n"
            f"💰 Макс. сделка: `${Config.MAX_TRADE_SIZE_USD}`\n"
            f"🛑 Дневной лимит: `${Config.DAILY_LOSS_LIMIT_USD}`"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="menu_trading")]]), parse_mode='Markdown')
