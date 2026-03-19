from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import binance_client as bc

ALERTS_KEY = 'price_alerts'

def get_alerts(context):
    if ALERTS_KEY not in context.bot_data:
        context.bot_data[ALERTS_KEY] = []
    return context.bot_data[ALERTS_KEY]

class AlertHandler:

    async def handle(self, query, context, data):
        action = data.split("_", 1)[1]
        if action == "price":
            await self._start(query, context)
        elif action == "list":
            await self._list(query, context)
        elif action == "clear":
            await self._clear(query, context)

    async def _start(self, query, context):
        context.user_data['waiting_alert_price'] = True
        context.user_data['alert_step'] = 'symbol'
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("BTC", callback_data="alert_sym_BTC"),
             InlineKeyboardButton("ETH", callback_data="alert_sym_ETH"),
             InlineKeyboardButton("BNB", callback_data="alert_sym_BNB"),
             InlineKeyboardButton("SOL", callback_data="alert_sym_SOL")],
            [InlineKeyboardButton("❌ Отмена", callback_data="menu_alerts")]
        ])
        await query.edit_message_text(
            "🔔 *Уведомление о цене (Price Alert)*\n\nИли напишите `/alert BTC 90000`\n\nСначала выберите монету (coin):",
            reply_markup=kb, parse_mode='Markdown'
        )

    async def process_alert_input(self, update: Update, context, text):
        step = context.user_data.get('alert_step', 'symbol')

        if step == 'symbol':
            symbol = text.upper().strip()
            if not symbol.endswith("USDT"):
                symbol += "USDT"
            context.user_data['alert_symbol'] = symbol
            context.user_data['alert_step'] = 'price'
            try:
                price = bc.get_price(symbol)
                await update.message.reply_text(
                    f"💰 {symbol} сейчас: `${price:,.4f}`\n\nВведите целевую цену (target price), например: `90000`",
                    parse_mode='Markdown'
                )
            except:
                await update.message.reply_text("Введите целевую цену (target price), например: `90000`", parse_mode='Markdown')

        elif step == 'price':
            try:
                price = float(text.replace('$', '').replace(',', '').strip())
                symbol = context.user_data.get('alert_symbol', 'BTCUSDT')
                user_id = update.effective_user.id
                alerts = get_alerts(context)
                alerts.append({
                    'id': len(alerts) + 1,
                    'user_id': user_id,
                    'symbol': symbol,
                    'target_price': price,
                    'active': True,
                    'last_price': None
                })
                context.user_data['waiting_alert_price'] = False
                context.user_data['alert_step'] = None
                current = bc.get_price(symbol)
                direction = "⬆️ Выше" if price > current else "⬇️ Ниже"
                await update.message.reply_text(
                    f"✅ *Уведомление создано!*\n\n"
                    f"🔔 `{symbol}` → `${price:,.4f}`\n"
                    f"💰 Сейчас: `${current:,.4f}`\n"
                    f"📍 Сработает: {direction} цели",
                    parse_mode='Markdown'
                )
            except ValueError:
                await update.message.reply_text("❌ Ошибка. Введите число, например: `90000`", parse_mode='Markdown')

    async def set_price_alert(self, update: Update, context, symbol, price):
        if not symbol.endswith("USDT"):
            symbol += "USDT"
        alerts = get_alerts(context)
        alerts.append({
            'id': len(alerts) + 1,
            'user_id': update.effective_user.id,
            'symbol': symbol,
            'target_price': price,
            'active': True,
            'last_price': None
        })
        await update.message.reply_text(
            f"✅ *Уведомление создано!*\n🔔 `{symbol}` → `${price:,.2f}`",
            parse_mode='Markdown'
        )

    async def _list(self, query, context):
        alerts = get_alerts(context)
        user_id = query.from_user.id
        my = [a for a in alerts if a.get('user_id') == user_id and a.get('active')]
        if not my:
            text = "📜 *Мои уведомления*\n\nАктивных уведомлений нет."
        else:
            text = f"📜 *Мои уведомления ({len(my)})*\n\n"
            for a in my:
                text += f"#{a['id']} 🔔 `{a['symbol']}` → `${a['target_price']:,.4f}`\n"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Удалить все", callback_data="alert_clear"),
            InlineKeyboardButton("🔙 Назад", callback_data="menu_alerts")
        ]])
        await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')

    async def _clear(self, query, context):
        user_id = query.from_user.id
        alerts = get_alerts(context)
        context.bot_data[ALERTS_KEY] = [a for a in alerts if a.get('user_id') != user_id]
        await query.edit_message_text(
            "✅ Все уведомления удалены.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="menu_alerts")]])
        )
