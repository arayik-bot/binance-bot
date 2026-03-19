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
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="menu_admin")]])

    async def _logs(self, query, context):
        logs = context.bot_data.get('log_history', [])
        text = "📜 *Последние логи (Logs)*\n\n"
        text += "\n".join([f"`{e}`" for e in logs[-15:]]) if logs else "Логов нет."
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Обновить", callback_data="admin_logs"),
            InlineKeyboardButton("🔙 Назад", callback_data="menu_admin")
        ]])
        await query.edit_message_text(text[:3500], reply_markup=kb, parse_mode='Markdown')

    async def _status(self, query, context):
        trading = context.bot_data.get('trading_active', False)
        alerts = len(context.bot_data.get('price_alerts', []))
        readonly = context.bot_data.get('runtime_readonly', Config.READ_ONLY)
        text = (
            f"🔍 *Статус бота (Bot Status)*\n\n"
            f"🤖 Авто торговля: {'🟢 Активна' if trading else '🔴 Остановлена'}\n"
            f"🔔 Активных уведомлений: `{alerts}`\n"
            f"🛡 Режим чтения (Read-Only): {'🟡 Вкл' if readonly else '🟢 Выкл'}\n"
            f"👥 Разрешённых пользователей: `{len(Config.ALLOWED_USERS)}`\n"
            f"💰 Макс. сделка: `${Config.MAX_TRADE_SIZE_USD}`\n"
            f"🛑 Дневной лимит: `${Config.DAILY_LOSS_LIMIT_USD}`\n"
            f"🐍 Python: `{sys.version.split()[0]}`\n"
            f"🌐 Сервер: Render (Frankfurt) ✅"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Обновить", callback_data="admin_status"),
            InlineKeyboardButton("🔙 Назад", callback_data="menu_admin")
        ]])
        await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')

    async def _toggle_readonly(self, query, context):
        cur = context.bot_data.get('runtime_readonly', Config.READ_ONLY)
        new = not cur
        context.bot_data['runtime_readonly'] = new
        state = "🟡 Включён — торговля ВЫКЛЮЧЕНА" if new else "🟢 Выключен — торговля АКТИВНА"
        text = f"🛡 *Режим чтения (Read-Only)*\n\nНовый статус: {state}"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Переключить", callback_data="admin_readonly"),
            InlineKeyboardButton("🔙 Назад", callback_data="menu_admin")
        ]])
        await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')

    async def _limits(self, query):
        text = (
            f"📊 *Управление рисками (Risk Management)*\n\n"
            f"💰 Макс. сделка: `${Config.MAX_TRADE_SIZE_USD}`\n"
            f"🛑 Дневной лимит убытков: `${Config.DAILY_LOSS_LIMIT_USD}`\n"
            f"⚡ Плечо фьючерсов (Leverage): `{Config.FUTURES_LEVERAGE}x`\n\n"
            f"Изменить через Render env vars:\n"
            f"`MAX_TRADE_SIZE_USD`\n"
            f"`DAILY_LOSS_LIMIT_USD`"
        )
        await query.edit_message_text(text, reply_markup=self._back(), parse_mode='Markdown')
