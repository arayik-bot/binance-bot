from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import binance_client as bc
import numpy as np
import logging
import io

logger = logging.getLogger(__name__)

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]


def sym_kb(action: str) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for s in SYMBOLS:
        short = s.replace("USDT", "")
        row.append(InlineKeyboardButton(short, callback_data=f"{action}_{s}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Hет", callback_data="menu_analysis")])
    return InlineKeyboardMarkup(rows)


def calc_rsi(closes, period=14):
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


def calc_macd(closes, fast=12, slow=26, signal=9):
    def ema(data, p):
        k = 2 / (p + 1)
        v = data[0]
        result = []
        for x in data:
            v = x * k + v * (1 - k)
            result.append(v)
        return result
    ef = ema(closes, fast)
    es = ema(closes, slow)
    macd = [f - s for f, s in zip(ef, es)]
    sig = ema(macd, signal)
    hist = [m - s for m, s in zip(macd, sig)]
    return macd[-1], sig[-1], hist[-1]


def calc_bb(closes, period=20, std=2):
    if len(closes) < period:
        return closes[-1], closes[-1], closes[-1]
    recent = closes[-period:]
    mid = np.mean(recent)
    s = np.std(recent)
    return mid + std * s, mid, mid - std * s


def find_sr(closes, window=10):
    highs, lows = [], []
    for i in range(window, len(closes) - window):
        if closes[i] == max(closes[i-window:i+window]):
            highs.append(closes[i])
        if closes[i] == min(closes[i-window:i+window]):
            lows.append(closes[i])
    res = max(highs[-3:]) if highs else closes[-1] * 1.02
    sup = min(lows[-3:]) if lows else closes[-1] * 0.98
    return sup, res


class AnalysisHandler:

    async def handle(self, query, context, data: str):
        parts = data.split("_", 2)
        action = parts[1]
        symbol = parts[2] if len(parts) > 2 else None

        if action == "rsi":
            if symbol:
                await self._rsi(query, symbol)
            else:
                await query.edit_message_text("📊 *RSI — Yntreq:*", reply_markup=sym_kb("analysis_rsi"), parse_mode='Markdown')
        elif action == "macd":
            if symbol:
                await self._macd(query, symbol)
            else:
                await query.edit_message_text("📈 *MACD — Yntreq:*", reply_markup=sym_kb("analysis_macd"), parse_mode='Markdown')
        elif action == "bb":
            if symbol:
                await self._bb(query, symbol)
            else:
                await query.edit_message_text("📉 *Bollinger — Yntreq:*", reply_markup=sym_kb("analysis_bb"), parse_mode='Markdown')
        elif action == "sr":
            if symbol:
                await self._sr(query, symbol)
            else:
                await query.edit_message_text("🎯 *S/R — Yntreq:*", reply_markup=sym_kb("analysis_sr"), parse_mode='Markdown')
        elif action == "signals":
            if symbol:
                await self._signals(query, symbol)
            else:
                await query.edit_message_text("📡 *Signals — Yntreq:*", reply_markup=sym_kb("analysis_signals"), parse_mode='Markdown')
        elif action == "chart":
            if symbol:
                await self._chart(query, context, symbol)
            else:
                await query.edit_message_text("📊 *Chart — Yntreq:*", reply_markup=sym_kb("analysis_chart"), parse_mode='Markdown')

    def _back(self, cb):
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Tharmacel", callback_data=cb),
            InlineKeyboardButton("🔙 Hет", callback_data="menu_analysis")
        ]])

    async def _rsi(self, query, symbol):
        try:
            closes = [float(k[4]) for k in bc.get_klines(symbol, "1h", 100)]
            rsi = calc_rsi(closes)
            closes4h = [float(k[4]) for k in bc.get_klines(symbol, "4h", 50)]
            rsi4h = calc_rsi(closes4h)
            if rsi < 30:
                status = "🟢 Oversold — BUY signal"
            elif rsi > 70:
                status = "🔴 Overbought — SELL signal"
            else:
                status = "⚪ Neutral"
            bar_n = int(rsi / 5)
            bar = "█" * bar_n + "░" * (20 - bar_n)
            text = (
                f"📊 *RSI — {symbol}*\n\n"
                f"1H RSI: `{rsi:.2f}`\n"
                f"`[{bar}]`\n\n"
                f"4H RSI: `{rsi4h:.2f}`\n\n"
                f"📝 {status}"
            )
            await query.edit_message_text(text, reply_markup=self._back(f"analysis_rsi_{symbol}"), parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Sxal: {e}")

    async def _macd(self, query, symbol):
        try:
            closes = [float(k[4]) for k in bc.get_klines(symbol, "1h", 100)]
            macd, sig, hist = calc_macd(closes)
            if macd > sig:
                status = "🟢 Bullish — MACD > Signal"
            else:
                status = "🔴 Bearish — MACD < Signal"
            text = (
                f"📈 *MACD — {symbol}*\n\n"
                f"MACD: `{macd:.6f}`\n"
                f"Signal: `{sig:.6f}`\n"
                f"Histogram: `{hist:+.6f}`\n\n"
                f"📝 {status}"
            )
            await query.edit_message_text(text, reply_markup=self._back(f"analysis_macd_{symbol}"), parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Sxal: {e}")

    async def _bb(self, query, symbol):
        try:
            closes = [float(k[4]) for k in bc.get_klines(symbol, "1h", 100)]
            upper, mid, lower = calc_bb(closes)
            cur = closes[-1]
            bw = ((upper - lower) / mid) * 100
            pos = ((cur - lower) / (upper - lower)) * 100 if upper != lower else 50
            if cur > upper:
                status = "🔴 Upper-ic vер — Overbought"
            elif cur < lower:
                status = "🟢 Lower-ic nerk — Oversold"
            else:
                status = "⚪ Bands mjuм"
            text = (
                f"📉 *Bollinger Bands — {symbol}*\n\n"
                f"⬆️ Upper: `${upper:,.4f}`\n"
                f"➡️ Middle: `${mid:,.4f}`\n"
                f"⬇️ Lower: `${lower:,.4f}`\n"
                f"💰 Hima: `${cur:,.4f}`\n\n"
                f"📏 Band Width: `{bw:.2f}%`\n"
                f"📍 Position: `{pos:.1f}%`\n\n"
                f"📝 {status}"
            )
            await query.edit_message_text(text, reply_markup=self._back(f"analysis_bb_{symbol}"), parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Sxal: {e}")

    async def _sr(self, query, symbol):
        try:
            klines = bc.get_klines(symbol, "4h", 100)
            closes = [float(k[4]) for k in klines]
            highs = [float(k[2]) for k in klines]
            lows = [float(k[3]) for k in klines]
            cur = closes[-1]
            sup, res = find_sr(closes)
            d_sup = ((cur - sup) / cur) * 100
            d_res = ((res - cur) / cur) * 100
            text = (
                f"🎯 *Support & Resistance — {symbol}*\n\n"
                f"🔴 Resistance: `${res:,.4f}` (+{d_res:.2f}%)\n"
                f"💰 Hima: `${cur:,.4f}`\n"
                f"🟢 Support: `${sup:,.4f}` (-{d_sup:.2f}%)\n\n"
                f"📊 Max: `${max(highs):,.4f}`\n"
                f"📊 Min: `${min(lows):,.4f}`"
            )
            await query.edit_message_text(text, reply_markup=self._back(f"analysis_sr_{symbol}"), parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Sxal: {e}")

    async def _signals(self, query, symbol):
        try:
            closes = [float(k[4]) for k in bc.get_klines(symbol, "1h", 100)]
            rsi = calc_rsi(closes)
            macd, sig, hist = calc_macd(closes)
            upper, mid, lower = calc_bb(closes)
            cur = closes[-1]
            score = 0
            lines = []

            if rsi < 30:
                lines.append("🟢 RSI Oversold (BUY)")
                score += 2
            elif rsi > 70:
                lines.append("🔴 RSI Overbought (SELL)")
                score -= 2
            else:
                lines.append(f"⚪ RSI Neutral ({rsi:.1f})")

            if macd > sig:
                lines.append("🟢 MACD Bullish")
                score += 1
            else:
                lines.append("🔴 MACD Bearish")
                score -= 1

            if cur < lower:
                lines.append("🟢 BB Below lower (BUY)")
                score += 2
            elif cur > upper:
                lines.append("🔴 BB Above upper (SELL)")
                score -= 2
            else:
                lines.append("⚪ BB Inside bands")

            if score >= 3:
                overall = "🟢 *STRONG BUY*"
            elif score >= 1:
                overall = "🟡 *WEAK BUY*"
            elif score <= -3:
                overall = "🔴 *STRONG SELL*"
            elif score <= -1:
                overall = "🟠 *WEAK SELL*"
            else:
                overall = "⚪ *NEUTRAL*"

            text = f"📡 *Signals — {symbol}*\n\n"
            for l in lines:
                text += f"• {l}\n"
            text += f"\n🏆 {overall}\nScore: `{score:+d}/5`"

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Tharmacel", callback_data=f"analysis_signals_{symbol}"),
                 InlineKeyboardButton("📊 Chart", callback_data=f"analysis_chart_{symbol}")],
                [InlineKeyboardButton("🟢 BUY", callback_data=f"trade_buy_{symbol}"),
                 InlineKeyboardButton("🔴 SELL", callback_data=f"trade_sell_{symbol}")],
                [InlineKeyboardButton("🔙 Hет", callback_data="menu_analysis")]
            ])
            await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ Sxal: {e}")

    async def _chart(self, query, context, symbol):
        await query.edit_message_text(f"📊 Generating chart {symbol}... ⏳")
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from datetime import datetime

            klines = bc.get_klines(symbol, "1h", 50)
            opens = [float(k[1]) for k in klines]
            highs = [float(k[2]) for k in klines]
            lows = [float(k[3]) for k in klines]
            closes = [float(k[4]) for k in klines]

            rsi_vals = []
            for i in range(len(closes)):
                rsi_vals.append(calc_rsi(closes[:max(i+1, 15)]))

            upper, mid, lower = calc_bb(closes)
            xs = list(range(len(closes)))

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8),
                                            facecolor='#1a1a2e',
                                            gridspec_kw={'height_ratios': [3, 1]})
            fig.suptitle(f'{symbol} — 1H Chart', color='white', fontsize=14)

            for ax in [ax1, ax2]:
                ax.set_facecolor('#16213e')
                ax.tick_params(colors='white')
                for spine in ax.spines.values():
                    spine.set_color('#333')

            for i in range(len(closes)):
                color = '#26a69a' if closes[i] >= opens[i] else '#ef5350'
                ax1.plot([i, i], [lows[i], highs[i]], color=color, linewidth=0.8)
                ax1.bar(i, abs(closes[i] - opens[i]), bottom=min(opens[i], closes[i]), color=color, width=0.6)

            ax1.axhline(upper, color='#ff9800', linestyle='--', linewidth=0.8, alpha=0.7, label=f'BB Upper')
            ax1.axhline(mid, color='#2196f3', linestyle='--', linewidth=0.8, alpha=0.7, label=f'BB Mid')
            ax1.axhline(lower, color='#ff9800', linestyle='--', linewidth=0.8, alpha=0.7, label=f'BB Lower')
            ax1.legend(facecolor='#16213e', labelcolor='white', fontsize=8)
            ax1.set_ylabel('Price (USDT)', color='white')
            ax1.set_xlim(-1, len(closes))

            ax2.plot(xs, rsi_vals, color='#ab47bc', linewidth=1.5)
            ax2.axhline(70, color='#ef5350', linestyle='--', linewidth=0.8, alpha=0.7)
            ax2.axhline(30, color='#26a69a', linestyle='--', linewidth=0.8, alpha=0.7)
            ax2.fill_between(xs, rsi_vals, 70, where=[r > 70 for r in rsi_vals], alpha=0.2, color='red')
            ax2.fill_between(xs, rsi_vals, 30, where=[r < 30 for r in rsi_vals], alpha=0.2, color='green')
            ax2.set_ylabel('RSI', color='white')
            ax2.set_ylim(0, 100)
            ax2.set_xlim(-1, len(closes))

            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='#1a1a2e')
            buf.seek(0)
            plt.close()

            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Tharmacel", callback_data=f"analysis_chart_{symbol}"),
                InlineKeyboardButton("🔙 Hет", callback_data="menu_analysis")
            ]])
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=buf,
                caption=f"📊 *{symbol} — 1H Chart* | Bollinger Bands + RSI",
                reply_markup=kb,
                parse_mode='Markdown'
            )
            await query.delete_message()

        except ImportError:
            await query.edit_message_text("❌ matplotlib teghtadrvac chi.",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Hет", callback_data="menu_analysis")]]))
        except Exception as e:
            await query.edit_message_text(f"❌ Sxal: {e}",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Hет", callback_data="menu_analysis")]]))
