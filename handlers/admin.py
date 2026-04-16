from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import Config
import sys

class AdminHandler:

    async def handle(self, query, context, data):
        action = data.split("_", 1)[1]
        if action == "logs": await self._logs(query, context)
        elif action == "status": await self._status(query, context)
        elif action == "readonly": await self._toggle_readonly(query, context)
        elif action == "limit": await self._limits(query)

    def _back(self):
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Հետ", callback_data="menu_admin")]])

    async def _logs(self, query, context):
        logs = context.bot_data.get('log_history', [])
        text = "📜 *Վերջին Լոգեր*\n\n━━━━━━━━━━━━━━━━━━\n"
        text += "\n".join([f"`{e}`" for e in logs[-15:]]) if logs else "Լոգեր չկան։"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Թարմացնել", callback_data="admin_logs"),
            InlineKeyboardButton("🔙 Հետ", callback_data="menu_admin")
        ]])
        await query.edit_message_text(text[:3500], reply_markup=kb, parse_mode='Markdown')

    async def _status(self, query, context):
        trading = context.bot_data.get('trading_active', False)
        alerts = len(context.bot_data.get('price_alerts', []))
        readonly = context.bot_data.get('runtime_readonly', Config.READ_ONLY)
        text = (
            f"🔍 *Բոտի Կարգավիճակ*\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🤖 Ավտո թրեյդինգ՝ {'🟢 Ակտիվ' if trading else '🔴 Կանգնած'}\n"
            f"🔔 Ակտիվ ծանուցումներ՝ `{alerts}`\n"
            f"🛡 Կարդալ-Միայն ռեժիմ՝ {'🟡 Միացված' if readonly else '🟢 Անջատված'}\n"
            f"👥 Թույլատրված օգտատերեր՝ `{len(Config.ALLOWED_USERS)}`\n"
            f"💰 Մաքս. գործարք՝ `${Config.MAX_TRADE_SIZE_USD}`\n"
            f"🛑 Օրական սահմանաչափ՝ `${Config.DAILY_LOSS_LIMIT_USD}`\n"
            f"🐍 Python՝ `{sys.version.split()[0]}`\n"
            f"🌐 Սервер՝ Render (Frankfurt) ✅"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Թարմացնել", callback_data="admin_status"),
            InlineKeyboardButton("🔙 Հետ", callback_data="menu_admin")
        ]])
        await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')

    async def _toggle_readonly(self, query, context):
        cur = context.bot_data.get('runtime_readonly', Config.READ_ONLY)
        new = not cur
        context.bot_data['runtime_readonly'] = new
        state = "🟡 Միացված — թրեյդինգն ԱՆՋԱՏՎԱԾ է" if new else "🟢 Անջատված — թրեյդինգն ԱԿՏԻՎ է"
        text = f"🛡 *Կարդալ-Միայն Ռեժիմ*\n\n━━━━━━━━━━━━━━━━━━\nՆոր կարգավիճակ՝ {state}"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Փոխել", callback_data="admin_readonly"),
            InlineKeyboardButton("🔙 Հետ", callback_data="menu_admin")
        ]])
        await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')

    async def _limits(self, query):
        text = (
            f"📊 *Ռիսկի Կառավարում*\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Մաքս. գործարք՝ `${Config.MAX_TRADE_SIZE_USD}`\n"
            f"🛑 Օրական վնասի սահմանաչափ՝ `${Config.DAILY_LOSS_LIMIT_USD}`\n"
            f"⚡ Ֆյուչերս լծակ՝ `{Config.FUTURES_LEVERAGE}x`\n\n"
            f"Փոխելու համար Render-ում՝\n"
            f"`MAX_TRADE_SIZE_USD`\n"
            f"`DAILY_LOSS_LIMIT_USD`"
        )
        await query.edit_message_text(text, reply_markup=self._back(), parse_mode='Markdown')
