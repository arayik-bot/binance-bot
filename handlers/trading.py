import asyncio
from binance_client import BinanceClient
from portfolio import Portfolio
import config

class TradingBot:
    def __init__(self):
        self.client = BinanceClient()
        self.portfolio = Portfolio()
        self.trading_enabled = True
        self.pending_trades = {}  # {user_id: {"signal": ..., "timeout_task": ...}}
    
    async def execute_trade(self, user_id, symbol, side, quantity_usd):
        if not self.trading_enabled or config.READ_ONLY_MODE:
            return {"error": "Trading disabled or read-only mode"}
        
        # Max size check
        if quantity_usd > config.MAX_TRADE_SIZE_USD:
            return {"error": f"Trade size exceeds limit (${config.MAX_TRADE_SIZE_USD})"}
        
        price = self.client.get_symbol_price(symbol)
        quantity = quantity_usd / price
        order = self.client.create_market_order(symbol, side, quantity)
        
        if "error" not in order:
            # Update PnL (simplified)
            self.portfolio.update_pnl(0)  # Realized PnL calculation omitted for brevity
        return order
    
    async def confirm_trade_flow(self, user_id, signal_data, usd_amount):
        """Send confirmation message, wait for response or auto-execute after timeout"""
        from bot import bot  # avoid circular import
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm", callback_data=f"confirm_{user_id}"),
             InlineKeyboardButton(text="❌ Cancel", callback_data=f"cancel_{user_id}")]
        ])
        
        msg = await bot.send_message(
            user_id,
            f"🟢 {signal_data['signal']} signal for {signal_data['symbol']}\n"
            f"💰 Amount: ${usd_amount}\n"
            f"⏳ Auto-execute in {config.CONFIRM_TIMEOUT} seconds...",
            reply_markup=keyboard
        )
        
        # Store pending trade
        task = asyncio.create_task(self._auto_execute_after_timeout(user_id, signal_data, usd_amount, msg.message_id))
        self.pending_trades[user_id] = {
            "signal": signal_data,
            "usd_amount": usd_amount,
            "message_id": msg.message_id,
            "timeout_task": task
        }
    
    async def _auto_execute_after_timeout(self, user_id, signal_data, usd_amount, message_id):
        await asyncio.sleep(config.CONFIRM_TIMEOUT)
        if user_id in self.pending_trades:
            # Auto execute
            result = await self.execute_trade(user_id, signal_data['symbol'], signal_data['signal'].lower(), usd_amount)
            from bot import bot
            await bot.edit_message_text(
                f"⏰ Auto-executed: {signal_data['signal']} {signal_data['symbol']} for ${usd_amount}\n"
                f"Result: {result}",
                chat_id=user_id,
                message_id=message_id
            )
            del self.pending_trades[user_id]
    
    async def cancel_pending_trade(self, user_id):
        if user_id in self.pending_trades:
            self.pending_trades[user_id]["timeout_task"].cancel()
            del self.pending_trades[user_id]
            return True
        return False
