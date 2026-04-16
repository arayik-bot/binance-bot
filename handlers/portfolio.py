from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import binance_client as bc


class PortfolioHandler:

    async def handle(self, query, context, data: str):
        action = data.split("_", 1)[1]
        if action == "spot":
            await self._spot(query)
        elif action == "futures":
            await self._futures(query)
        elif action == "orders":
            await self._orders(query)
        elif action == "history":
            await self._history(query, context)
        elif action == "pnl":
            await self._pnl(query)
        elif action == "allocation":
            await self._allocation(query)

    def _back(self, cb="menu_portfolio"):
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Հետ", callback_data=cb)]])

    async def _spot(self, query):
        try:
            balances = bc.get_spot_balance()
            if not balances:
                await query.edit_message_text("💼 Սփոթ բալանսը դատարկ է։", reply_markup=self._back())
                return
            text = "💰 *Սփոթ Բալանս*\n\n━━━━━━━━━━━━━━━━━━\n"
            for b in balances[:15]:
                free = float(b['free'])
                locked = float(b['locked'])
                text += f"🪙 `{b['asset']}`: ազատ=`{free:.6f}` կողպված=`{locked:.6f}`\n"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Թարմացնել", callback_data="portfolio_spot"),
                InlineKeyboardButton("🔙 Հետ", callback_data="menu_portfolio")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Սխալ՝ {e}\n\nAPI key-ը սխալ է կամ թույլտվություն չկա։", reply_markup=self._back())

    async def _futures(self, query):
        try:
            assets = bc.get_futures_balance()
            positions = bc.get_futures_positions()
            text = "📊 *Ֆյուչերս Բալանս*\n\n━━━━━━━━━━━━━━━━━━\n"
            for a in assets:
                if float(a['walletBalance']) > 0:
                    text += (
                        f"🪙 `{a['asset']}`\n"
                        f"  Wallet՝ `{float(a['walletBalance']):.4f}`\n"
                        f"  Չիրացված PnL՝ `{float(a['unrealizedProfit']):+.4f}`\n\n"
                    )
            if positions:
                text += "📋 *Բաց Պոզիցիաներ՝*\n"
                for p in positions:
                    side = "LONG" if float(p['positionAmt']) > 0 else "SHORT"
                    pnl = float(p['unrealizedProfit'])
                    e = "📈" if pnl >= 0 else "📉"
                    text += f"{e} `{p['symbol']}` {side} PnL՝ `{pnl:+.4f}`\n"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Թարմացնել", callback_data="portfolio_futures"),
                InlineKeyboardButton("🔙 Հետ", callback_data="menu_portfolio")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Սխալ՝ {e}", reply_markup=self._back())

    async def _orders(self, query):
        try:
            orders = bc.get_open_orders()
            if not orders:
                text = "📋 *Բաց Օրդերներ*\n\n━━━━━━━━━━━━━━━━━━\n✅ Ակտիվ օրդերներ չկան։"
            else:
                text = f"📋 *Բաց Օրդերներ ({len(orders)})*\n\n━━━━━━━━━━━━━━━━━━\n"
                for o in orders[:10]:
                    e = "🟢" if o['side'] == 'BUY' else "🔴"
                    text += f"{e} `{o['symbol']}` {o['side']} qty=`{o['origQty']}` @ `${float(o['price']):.4f}`\n"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Թարմացնել", callback_data="portfolio_orders"),
                InlineKeyboardButton("🔙 Հետ", callback_data="menu_portfolio")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Սխալ՝ {e}", reply_markup=self._back())

    async def _history(self, query, context):
        symbol = context.user_data.get('symbol', 'BTCUSDT')
        try:
            trades = bc.get_trade_history(symbol, 10)
            if not trades:
                text = f"📜 *Գործարքների Պատմություն — {symbol}*\n\n━━━━━━━━━━━━━━━━━━\nԳործարքներ չկան։"
            else:
                text = f"📜 *Վերջին Գործարքներ — {symbol}*\n\n━━━━━━━━━━━━━━━━━━\n"
                for t in trades:
                    e = "🟢" if t['isBuyer'] else "🔴"
                    action = "ԳՆԵ" if t['isBuyer'] else "ՎԱՃԱ"
                    text += f"{e} {action} {t['qty']} @ `${float(t['price']):.4f}`\n"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Թարմացնել", callback_data="portfolio_history"),
                InlineKeyboardButton("🔙 Հետ", callback_data="menu_portfolio")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Սխալ՝ {e}", reply_markup=self._back())

    async def _pnl(self, query):
        try:
            positions = bc.get_futures_positions()
            text = "💹 *Շահույթ/Վնաս (PnL)*\n\n━━━━━━━━━━━━━━━━━━\n"
            if not positions:
                text += "Ակտիվ ֆյուչերս պոզիցիաներ չկան։"
            else:
                total = 0
                for p in positions:
                    pnl = float(p['unrealizedProfit'])
                    total += pnl
                    side = "LONG" if float(p['positionAmt']) > 0 else "SHORT"
                    e = "📈" if pnl >= 0 else "📉"
                    text += f"{e} `{p['symbol']}` {side}\n  PnL՝ `{pnl:+.4f} USDT`\n  Մուտք՝ `${float(p['entryPrice']):.4f}`\n\n"
                e2 = "📈" if total >= 0 else "📉"
                text += f"━━━━━━━━━━━━━━━━━━\n{e2} *Ընդամենը՝ `{total:+.4f} USDT`*"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Թարմացնել", callback_data="portfolio_pnl"),
                InlineKeyboardButton("🔙 Հետ", callback_data="menu_portfolio")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Սխալ՝ {e}", reply_markup=self._back())

    async def _allocation(self, query):
        try:
            balances = bc.get_spot_balance()
            usdt_vals = {}
            total = 0
            for b in balances:
                asset = b['asset']
                amt = float(b['free']) + float(b['locked'])
                if asset == 'USDT':
                    usdt_vals[asset] = amt
                    total += amt
                elif amt > 0:
                    try:
                        price = bc.get_price(f"{asset}USDT")
                        val = amt * price
                        usdt_vals[asset] = val
                        total += val
                    except:
                        pass
            text = "🥧 *Ակտիվների Բաշխում*\n\n━━━━━━━━━━━━━━━━━━\n"
            if total > 0:
                for asset, val in sorted(usdt_vals.items(), key=lambda x: x[1], reverse=True)[:10]:
                    pct = (val / total) * 100
                    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                    text += f"`{asset:8}` `{pct:.1f}%` ~`${val:.2f}`\n"
                text += f"\n━━━━━━━━━━━━━━━━━━\n💰 *Ընդամենը՝ ~${total:.2f} USDT*"
            else:
                text += "Բալանսը դատարկ է։"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Թարմացնել", callback_data="portfolio_allocation"),
                InlineKeyboardButton("🔙 Հետ", callback_data="menu_portfolio")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Սխալ՝ {e}", reply_markup=self._back())
