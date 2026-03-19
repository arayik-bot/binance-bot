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
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Hет", callback_data=cb)]])

    async def _spot(self, query):
        try:
            balances = bc.get_spot_balance()
            if not balances:
                await query.edit_message_text("💼 Spot balance datark e.", reply_markup=self._back())
                return
            text = "💰 *Spot Balance*\n\n"
            for b in balances[:15]:
                free = float(b['free'])
                locked = float(b['locked'])
                text += f"🪙 `{b['asset']}`: free=`{free:.6f}` locked=`{locked:.6f}`\n"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Tharmacel", callback_data="portfolio_spot"),
                InlineKeyboardButton("🔙 Hет", callback_data="menu_portfolio")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Sxal: {e}\n\nAPI key-y sxal e kam ijravutyun chi.", reply_markup=self._back())

    async def _futures(self, query):
        try:
            assets = bc.get_futures_balance()
            positions = bc.get_futures_positions()
            text = "📊 *Futures Balance*\n\n"
            for a in assets:
                if float(a['walletBalance']) > 0:
                    text += (
                        f"🪙 `{a['asset']}`\n"
                        f"  Wallet: `{float(a['walletBalance']):.4f}`\n"
                        f"  Unrealized PnL: `{float(a['unrealizedProfit']):+.4f}`\n\n"
                    )
            if positions:
                text += "📋 *Open Positions:*\n"
                for p in positions:
                    side = "LONG" if float(p['positionAmt']) > 0 else "SHORT"
                    pnl = float(p['unrealizedProfit'])
                    e = "📈" if pnl >= 0 else "📉"
                    text += f"{e} `{p['symbol']}` {side} PnL: `{pnl:+.4f}`\n"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Tharmacel", callback_data="portfolio_futures"),
                InlineKeyboardButton("🔙 Hет", callback_data="menu_portfolio")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Sxal: {e}", reply_markup=self._back())

    async def _orders(self, query):
        try:
            orders = bc.get_open_orders()
            if not orders:
                text = "📋 *Open Orders*\n\n✅ Activ orders ckan."
            else:
                text = f"📋 *Open Orders ({len(orders)})*\n\n"
                for o in orders[:10]:
                    e = "🟢" if o['side'] == 'BUY' else "🔴"
                    text += f"{e} `{o['symbol']}` {o['side']} qty=`{o['origQty']}` @ `${float(o['price']):.4f}`\n"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Tharmacel", callback_data="portfolio_orders"),
                InlineKeyboardButton("🔙 Hет", callback_data="menu_portfolio")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Sxal: {e}", reply_markup=self._back())

    async def _history(self, query, context):
        symbol = context.user_data.get('symbol', 'BTCUSDT')
        try:
            trades = bc.get_trade_history(symbol, 10)
            if not trades:
                text = f"📜 *Trade History — {symbol}*\n\nGorcarqner ckan."
            else:
                text = f"📜 *Last Trades — {symbol}*\n\n"
                for t in trades:
                    e = "🟢" if t['isBuyer'] else "🔴"
                    action = "BUY" if t['isBuyer'] else "SELL"
                    text += f"{e} {action} {t['qty']} @ `${float(t['price']):.4f}`\n"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Tharmacel", callback_data="portfolio_history"),
                InlineKeyboardButton("🔙 Hет", callback_data="menu_portfolio")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Sxal: {e}", reply_markup=self._back())

    async def _pnl(self, query):
        try:
            positions = bc.get_futures_positions()
            text = "💹 *PnL Report*\n\n"
            if not positions:
                text += "Activ futures positions ckan."
            else:
                total = 0
                for p in positions:
                    pnl = float(p['unrealizedProfit'])
                    total += pnl
                    side = "LONG" if float(p['positionAmt']) > 0 else "SHORT"
                    e = "📈" if pnl >= 0 else "📉"
                    text += f"{e} `{p['symbol']}` {side}\n  PnL: `{pnl:+.4f} USDT`\n  Entry: `${float(p['entryPrice']):.4f}`\n\n"
                e2 = "📈" if total >= 0 else "📉"
                text += f"{e2} *Total: `{total:+.4f} USDT`*"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Tharmacel", callback_data="portfolio_pnl"),
                InlineKeyboardButton("🔙 Hет", callback_data="menu_portfolio")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Sxal: {e}", reply_markup=self._back())

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
            text = "🥧 *Asset Allocation*\n\n"
            if total > 0:
                for asset, val in sorted(usdt_vals.items(), key=lambda x: x[1], reverse=True)[:10]:
                    pct = (val / total) * 100
                    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                    text += f"`{asset:8}` `{pct:.1f}%` ~`${val:.2f}`\n"
                text += f"\n💰 *Total: ~${total:.2f} USDT*"
            else:
                text += "Balance datark e."
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Tharmacel", callback_data="portfolio_allocation"),
                InlineKeyboardButton("🔙 Hет", callback_data="menu_portfolio")
            ]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Sxal: {e}", reply_markup=self._back())
