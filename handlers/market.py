from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import binance_client as bc

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT"]

def sym_keyboard(action):
    rows = []
    row = []
    for s in SYMBOLS:
        short = s.replace("USDT", "")
        row.append(InlineKeyboardButton(short, callback_data=f"{action}_{s}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="menu_market")])
    return InlineKeyboardMarkup(rows)

def back_kb(cb):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Обновить", callback_data=cb),
        InlineKeyboardButton("🔙 Назад", callback_data="menu_market")
    ]])

class MarketHandler:
    async def handle(self, query, context, data):
        parts = data.split("_", 2)
        action = parts[1]
        symbol = parts[2] if len(parts) > 2 else None

        if action == "price":
            if symbol: await self._price(query, symbol)
            else: await query.edit_message_text("💰 *Выберите монету (coin):*", reply_markup=sym_keyboard("market_price"), parse_mode='Markdown')
        elif action == "stats":
            if symbol: await self._stats(query, symbol)
            else: await query.edit_message_text("📊 *Статистика 24ч — Выберите:*", reply_markup=sym_keyboard("market_stats"), parse_mode='Markdown')
        elif action == "orderbook":
            if symbol: await self._orderbook(query, symbol)
            else: await query.edit_message_text("📖 *Стакан (Order Book) — Выберите:*", reply_markup=sym_keyboard("market_orderbook"), parse_mode='Markdown')
        elif action == "candles":
            if symbol: await self._candles(query, symbol)
            else: await query.edit_message_text("🕯 *Свечи (Candles) — Выберите:*", reply_markup=sym_keyboard("market_candles"), parse_mode='Markdown')
        elif action == "gainers": await self._gainers(query)
        elif action == "losers": await self._losers(query)
        elif action == "funding":
            if symbol: await self._funding(query, symbol)
            else: await query.edit_message_text("💸 *Ставка финансирования (Funding) — Выберите:*", reply_markup=sym_keyboard("market_funding"), parse_mode='Markdown')

    async def _price(self, query, symbol):
        try:
            price = bc.get_price(symbol)
            await query.edit_message_text(
                f"💰 *{symbol}*\n\nЦена (Price): `${price:,.4f}`",
                reply_markup=back_kb(f"market_price_{symbol}"), parse_mode='Markdown'
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="menu_market")]]))

    async def _stats(self, query, symbol):
        try:
            s = bc.get_24h_stats(symbol)
            pct = float(s['priceChangePercent'])
            e = "📈" if pct >= 0 else "📉"
            text = (
                f"📊 *{symbol} — 24 часа*\n\n"
                f"💰 Цена (Price): `${float(s['lastPrice']):,.4f}`\n"
                f"{e} Изменение (Change): `{pct:+.2f}%`\n"
                f"⬆️ Максимум (High): `${float(s['highPrice']):,.4f}`\n"
                f"⬇️ Минимум (Low): `${float(s['lowPrice']):,.4f}`\n"
                f"📦 Объём (Volume): `{float(s['volume']):,.2f}`\n"
                f"🔢 Сделки (Trades): `{s['count']:,}`"
            )
            await query.edit_message_text(text, reply_markup=back_kb(f"market_stats_{symbol}"), parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")

    async def _orderbook(self, query, symbol):
        try:
            ob = bc.get_order_book(symbol, 5)
            bids = ob['bids'][:5]
            asks = ob['asks'][:5]
            text = f"📖 *{symbol} Стакан (Order Book)*\n\n🟢 *Покупка (Bids)*\n"
            for p, q in bids:
                text += f"  `${float(p):,.4f}` — `{float(q):.4f}`\n"
            text += "\n🔴 *Продажа (Asks)*\n"
            for p, q in asks:
                text += f"  `${float(p):,.4f}` — `{float(q):.4f}`\n"
            spread = float(asks[0][0]) - float(bids[0][0])
            text += f"\n📏 Спред (Spread): `${spread:.4f}`"
            await query.edit_message_text(text, reply_markup=back_kb(f"market_orderbook_{symbol}"), parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")

    async def _candles(self, query, symbol):
        try:
            klines = bc.get_klines(symbol, "1h", 5)
            text = f"🕯 *{symbol} — Последние 5 свечей (1ч)*\n\n"
            for k in klines:
                o, h, l, c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
                emoji = "🟢" if c >= o else "🔴"
                pct = ((c - o) / o) * 100
                text += (
                    f"{emoji} `{pct:+.2f}%`\n"
                    f"  О: `${o:,.2f}`\n"
                    f"  В: `${h:,.2f}`\n"
                    f"  Н: `${l:,.2f}`\n"
                    f"  З: `${c:,.2f}`\n\n"
                )
            await query.edit_message_text(text, reply_markup=back_kb(f"market_candles_{symbol}"), parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")

    async def _gainers(self, query):
        try:
            gainers = bc.get_top_gainers(10)
            text = "🏆 *Лидеры роста (Top Gainers) за 24ч*\n\n"
            for i, t in enumerate(gainers, 1):
                pct = float(t['priceChangePercent'])
                text += f"{i}. `{t['symbol']}` 📈 `+{pct:.2f}%` `${float(t['lastPrice']):.4f}`\n"
            await query.edit_message_text(text, reply_markup=back_kb("market_gainers"), parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")

    async def _losers(self, query):
        try:
            losers = bc.get_top_losers(10)
            text = "📉 *Лидеры падения (Top Losers) за 24ч*\n\n"
            for i, t in enumerate(losers, 1):
                pct = float(t['priceChangePercent'])
                text += f"{i}. `{t['symbol']}` 📉 `{pct:.2f}%` `${float(t['lastPrice']):.4f}`\n"
            await query.edit_message_text(text, reply_markup=back_kb("market_losers"), parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")

    async def _funding(self, query, symbol):
        try:
            rate = bc.get_futures_funding_rate(symbol)
            if rate:
                fr = float(rate['fundingRate']) * 100
                text = (
                    f"💸 *{symbol} Ставка финансирования (Funding Rate)*\n\n"
                    f"Ставка: `{fr:.4f}%`\n"
                    f"{'📈 Long платит Short' if fr > 0 else '📉 Short платит Long'}"
                )
            else:
                text = f"❌ Funding rate для {symbol} не найден"
            await query.edit_message_text(text, reply_markup=back_kb(f"market_funding_{symbol}"), parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")

    async def get_price(self, update: Update, context, symbol: str):
        try:
            price = bc.get_price(symbol)
            await update.message.reply_text(f"💰 *{symbol}*: `${price:,.4f}`", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")