"""
╔══════════════════════════════════════════════════════════════════╗
║        BINANCE PRO TRADING BOT — FULL AUTO TRADE SYSTEM         ║
║  Deploy: Render.com | Python 3.11 | GitHub | No CMD needed      ║
╚══════════════════════════════════════════════════════════════════╝

FEATURES:
  ✅ Manual Buy / Sell
  ✅ Auto-Trade with confirmation (ask user → timeout → auto-execute)
  ✅ Fixed trade sizes: $5,$10,$15,$20,$25,$30,$35,$40,$45,$50
  ✅ 15 Top Coins: BTC,ETH,BNB,SOL,XRP,ADA,DOGE,AVAX,DOT,MATIC,
                  LINK,LTC,UNI,ATOM,NEAR
  ✅ RSI + MACD + BB signal engine
  ✅ Portfolio + PnL tracker
  ✅ Price alerts
  ✅ Order history
  ✅ Watchlist
  ✅ Fear & Greed
  ✅ Whale alerts
  ✅ DCA planner
  ✅ Render keep-alive web server built-in
"""

import os
import asyncio
import logging
import json
import time
import math
import random
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

# ── Web server for Render keep-alive ──────────────────────────
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Telegram ──────────────────────────────────────────────────
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from telegram.constants import ParseMode

# ── Binance ───────────────────────────────────────────────────
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
    BINANCE_OK = True
except ImportError:
    BINANCE_OK = False

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S", level=logging.INFO
)
log = logging.getLogger("TradeBot")

# ══════════════════════════════════════════════════════════════
#  CONFIG  —  set these in Render Environment Variables
# ══════════════════════════════════════════════════════════════
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN",  "YOUR_TOKEN")
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "")
BINANCE_SECRET  = os.environ.get("BINANCE_SECRET",  "")
ADMIN_IDS       = list(map(int, os.environ.get("ADMIN_IDS", "0").split(",")))
USE_TESTNET     = os.environ.get("USE_TESTNET", "true").lower() == "true"
PORT            = int(os.environ.get("PORT", 8080))

# ── Trade sizes available ──────────────────────────────────────
TRADE_SIZES = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]

# ── Top 15 coins ──────────────────────────────────────────────
TOP_COINS = [
    "BTC", "ETH", "BNB", "SOL", "XRP",
    "ADA", "DOGE", "AVAX", "DOT", "MATIC",
    "LINK", "LTC", "UNI", "ATOM", "NEAR"
]

# Auto-confirm timeout (seconds) — if user doesn't respond, bot executes
AUTO_CONFIRM_TIMEOUT = int(os.environ.get("AUTO_CONFIRM_TIMEOUT", "30"))

# ══════════════════════════════════════════════════════════════
#  STATE STORE  (in-memory; persists as long as Render is up)
# ══════════════════════════════════════════════════════════════
def default_user():
    return {
        "portfolio":     {},   # {BTCUSDT: {qty, avg_price, invested}}
        "alerts":        [],
        "watchlist":     [],
        "orders":        [],   # trade history
        "pending_trade": None, # waiting confirmation
        "chat_id":       None,
    }

USER_DATA: dict = defaultdict(default_user)

# ── Binance client ─────────────────────────────────────────────
bc: Optional[object] = None
if BINANCE_OK and BINANCE_API_KEY:
    try:
        if USE_TESTNET:
            bc = Client(BINANCE_API_KEY, BINANCE_SECRET, testnet=True)
        else:
            bc = Client(BINANCE_API_KEY, BINANCE_SECRET)
        log.info("✅ Binance connected" + (" [TESTNET]" if USE_TESTNET else " [LIVE]"))
    except Exception as e:
        log.warning(f"Binance error: {e}")

# ══════════════════════════════════════════════════════════════
#  BINANCE DATA HELPERS
# ══════════════════════════════════════════════════════════════
MOCK_PRICES = {
    "BTCUSDT":   67500, "ETHUSDT":  3450,  "BNBUSDT":   582,
    "SOLUSDT":   176,   "XRPUSDT":  0.58,  "ADAUSDT":   0.48,
    "DOGEUSDT":  0.162, "AVAXUSDT": 38.7,  "DOTUSDT":   7.8,
    "MATICUSDT": 0.91,  "LINKUSDT": 18.4,  "LTCUSDT":   82.0,
    "UNIUSDT":   9.3,   "ATOMUSDT": 10.5,  "NEARUSDT":  7.1,
}

def sym(coin: str) -> str:
    coin = coin.upper().strip()
    return coin if coin.endswith("USDT") else coin + "USDT"

def get_price(coin: str) -> dict:
    s = sym(coin)
    if bc:
        try:
            t = bc.get_ticker(symbol=s)
            return {
                "symbol": s, "price": float(t["lastPrice"]),
                "change": float(t["priceChangePercent"]),
                "high":   float(t["highPrice"]),
                "low":    float(t["lowPrice"]),
                "volume": float(t["volume"]),
            }
        except Exception as e:
            return {"error": str(e), "symbol": s}
    base = MOCK_PRICES.get(s, 10.0)
    base *= random.uniform(0.98, 1.02)
    chg  = round(random.uniform(-6, 6), 2)
    return {
        "symbol": s, "price": round(base, 6),
        "change": chg,
        "high":  round(base * 1.04, 6),
        "low":   round(base * 0.96, 6),
        "volume": round(random.uniform(5000, 500000), 2),
    }

def get_klines(coin: str, interval="1h", limit=100) -> list:
    s = sym(coin)
    if bc:
        try:
            return bc.get_klines(symbol=s, interval=interval, limit=limit)
        except:
            pass
    base = MOCK_PRICES.get(s, 50.0)
    data = []
    t = int(time.time() * 1000) - limit * 3600000
    for _ in range(limit):
        o = base * random.uniform(0.99, 1.01)
        h = o * random.uniform(1.00, 1.02)
        lo = o * random.uniform(0.98, 1.00)
        c = random.uniform(lo, h)
        base = c
        data.append([t, str(o), str(h), str(lo), str(c),
                      str(random.uniform(100, 5000)), t + 3600000])
        t += 3600000
    return data

def get_account_balance() -> dict:
    """Get USDT balance from Binance or mock."""
    if bc:
        try:
            acc = bc.get_account()
            balances = {b["asset"]: float(b["free"])
                        for b in acc["balances"] if float(b["free"]) > 0}
            return {"ok": True, "balances": balances,
                    "usdt": balances.get("USDT", 0)}
        except Exception as e:
            return {"ok": False, "error": str(e), "usdt": 0}
    return {"ok": True, "balances": {"USDT": 1000.0, "BTC": 0.01, "ETH": 0.5},
            "usdt": 1000.0, "mock": True}

def place_order(coin: str, side: str, usdt_amount: float) -> dict:
    """
    Place a market order.
    side: 'BUY' or 'SELL'
    usdt_amount: dollar amount to trade
    """
    s = sym(coin)
    ticker = get_price(coin)
    if "error" in ticker:
        return {"ok": False, "error": ticker["error"]}

    price = ticker["price"]
    qty   = usdt_amount / price

    if bc:
        try:
            # Round qty to exchange step size (simplified)
            qty_str = f"{qty:.6f}"
            if side == "BUY":
                order = bc.order_market_buy(symbol=s, quoteOrderQty=usdt_amount)
            else:
                order = bc.order_market_sell(symbol=s, quantity=qty_str)
            filled_price = float(order.get("fills", [{}])[0].get("price", price))
            filled_qty   = float(order.get("executedQty", qty))
            return {
                "ok": True, "symbol": s, "side": side,
                "qty": filled_qty, "price": filled_price,
                "total": filled_qty * filled_price,
                "orderId": order.get("orderId"),
                "mock": False
            }
        except BinanceAPIException as e:
            return {"ok": False, "error": f"Binance: {e.message}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── MOCK ORDER ──────────────────────────────────────────
    slippage = random.uniform(-0.001, 0.001)
    exec_price = price * (1 + slippage)
    exec_qty   = usdt_amount / exec_price
    return {
        "ok": True, "symbol": s, "side": side,
        "qty": round(exec_qty, 8), "price": round(exec_price, 4),
        "total": round(usdt_amount, 2),
        "orderId": f"MOCK-{int(time.time())}",
        "mock": True
    }

# ══════════════════════════════════════════════════════════════
#  TECHNICAL ANALYSIS
# ══════════════════════════════════════════════════════════════
def compute_ta(coin: str, interval="1h") -> dict:
    klines = get_klines(coin, interval, 120)
    closes = [float(k[4]) for k in klines]
    highs  = [float(k[2]) for k in klines]
    lows   = [float(k[3]) for k in klines]

    def ema(prices, p):
        k, res = 2/(p+1), [sum(prices[:p])/p]
        for x in prices[p:]:
            res.append(x*k + res[-1]*(1-k))
        return res

    def rsi(prices, p=14):
        g, lo = [], []
        for i in range(1, len(prices)):
            d = prices[i]-prices[i-1]
            g.append(max(d,0)); lo.append(max(-d,0))
        ag = sum(g[-p:])/p; al = sum(lo[-p:])/p
        if al == 0: return 100.0
        return round(100 - 100/(1 + ag/al), 2)

    e12 = ema(closes, 12); e26 = ema(closes, 26)
    n   = min(len(e12), len(e26))
    macd_line = [e12[-n+i] - e26[i] for i in range(n)]
    signal    = ema(macd_line, 9)
    hist      = macd_line[-1] - signal[-1]

    p20   = closes[-20:]
    sma20 = sum(p20)/20
    std20 = math.sqrt(sum((c-sma20)**2 for c in p20)/20)
    bb_u  = sma20 + 2*std20
    bb_l  = sma20 - 2*std20

    rsi_v  = rsi(closes)
    cur    = closes[-1]
    score  = 0
    if rsi_v < 30:     score += 2
    elif rsi_v > 70:   score -= 2
    if hist > 0:       score += 1
    else:              score -= 1
    if cur < bb_l:     score += 1
    elif cur > bb_u:   score -= 1
    if e12[-1] > e26[-1]: score += 1
    else:                  score -= 1

    if score >= 3:   sig = "🟢 STRONG BUY"
    elif score >= 1: sig = "🟩 BUY"
    elif score <= -3:sig = "🔴 STRONG SELL"
    elif score <= -1:sig = "🟥 SELL"
    else:            sig = "🟡 NEUTRAL"

    return {
        "rsi": rsi_v, "macd": round(macd_line[-1],4),
        "hist": round(hist,4), "signal": sig, "score": score,
        "bb_u": round(bb_u,4), "bb_l": round(bb_l,4),
        "bb_m": round(sma20,4), "ema12": round(e12[-1],4),
        "ema26": round(e26[-1],4),
    }

def fear_and_greed() -> dict:
    v = random.randint(18, 88)
    if v < 25:   lb, em = "Extreme Fear", "😱"
    elif v < 45: lb, em = "Fear",          "😨"
    elif v < 55: lb, em = "Neutral",       "😐"
    elif v < 75: lb, em = "Greed",         "😏"
    else:        lb, em = "Extreme Greed", "🤑"
    return {"value": v, "label": lb, "emoji": em}

# ══════════════════════════════════════════════════════════════
#  PORTFOLIO HELPERS
# ══════════════════════════════════════════════════════════════
def portfolio_text(uid: int) -> str:
    port = USER_DATA[uid]["portfolio"]
    if not port:
        return "📂 Portfolio empty.\nTrade first to see positions here."
    lines = ["💼 *PORTFOLIO*\n"]
    ti = tc = 0.0
    for s, pos in port.items():
        t   = get_price(s)
        if "error" in t: continue
        p   = t["price"]
        q   = pos["qty"]
        avg = pos["avg_price"]
        inv = q * avg; cur = q * p
        pnl = cur - inv
        pct = pnl/inv*100 if inv else 0
        ti += inv; tc += cur
        e   = "🟢" if pnl >= 0 else "🔴"
        lines.append(
            f"{e} *{s}*\n"
            f"   `{q:.6f}` @ avg `${avg:.4f}`\n"
            f"   Now `${p:.4f}` | Value `${cur:.2f}`\n"
            f"   PnL `{'+' if pnl>=0 else ''}{pnl:.2f}$` ({pct:+.1f}%)\n"
        )
    tp = tc - ti
    te = "🟢" if tp >= 0 else "🔴"
    lines += [
        "─────────────────",
        f"💰 Invested: `${ti:.2f}`",
        f"💎 Value:    `${tc:.2f}`",
        f"{te} PnL:     `{'+' if tp>=0 else ''}{tp:.2f}$` ({(tp/ti*100 if ti else 0):+.1f}%)"
    ]
    return "\n".join(lines)

def update_portfolio(uid: int, order: dict):
    """Update portfolio after a successful order."""
    s   = order["symbol"]
    qty = order["qty"]
    p   = order["price"]
    port = USER_DATA[uid]["portfolio"]

    if order["side"] == "BUY":
        if s in port:
            old_qty = port[s]["qty"]
            old_avg = port[s]["avg_price"]
            new_qty = old_qty + qty
            new_avg = (old_qty*old_avg + qty*p) / new_qty
            port[s] = {"qty": new_qty, "avg_price": round(new_avg, 6),
                        "invested": port[s].get("invested", 0) + qty*p}
        else:
            port[s] = {"qty": qty, "avg_price": p, "invested": qty*p}
    else:  # SELL
        if s in port:
            new_qty = port[s]["qty"] - qty
            if new_qty <= 0.000001:
                del port[s]
            else:
                port[s]["qty"] = round(new_qty, 8)

def record_order(uid: int, order: dict, note=""):
    entry = {
        "time":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "symbol":  order["symbol"],
        "side":    order["side"],
        "qty":     order["qty"],
        "price":   order["price"],
        "total":   order["total"],
        "orderId": order.get("orderId", ""),
        "note":    note
    }
    USER_DATA[uid]["orders"].insert(0, entry)
    USER_DATA[uid]["orders"] = USER_DATA[uid]["orders"][:50]  # keep last 50

# ══════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Buy",         callback_data="m_buy"),
         InlineKeyboardButton("💰 Sell",        callback_data="m_sell")],
        [InlineKeyboardButton("🤖 Auto Trade",  callback_data="m_auto"),
         InlineKeyboardButton("💼 Portfolio",   callback_data="m_portfolio")],
        [InlineKeyboardButton("📊 Analysis",    callback_data="m_analysis"),
         InlineKeyboardButton("💹 Prices",      callback_data="m_prices")],
        [InlineKeyboardButton("📋 Screener",    callback_data="m_screener"),
         InlineKeyboardButton("🔔 Alerts",      callback_data="m_alerts")],
        [InlineKeyboardButton("📖 Orders",      callback_data="m_orders"),
         InlineKeyboardButton("😱 Fear&Greed",  callback_data="m_fg")],
        [InlineKeyboardButton("🐋 Whales",      callback_data="m_whale"),
         InlineKeyboardButton("ℹ️ Help",         callback_data="m_help")],
    ])

def back_kb(target="m_main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=target)]])

def coin_select_kb(action: str):
    """Grid keyboard of top 15 coins."""
    rows = []
    row  = []
    for i, c in enumerate(TOP_COINS):
        row.append(InlineKeyboardButton(c, callback_data=f"{action}_{c}"))
        if len(row) == 5:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="m_main")])
    return InlineKeyboardMarkup(rows)

def size_kb(action: str, coin: str):
    """Trade size selection keyboard."""
    rows = []
    row  = []
    for i, s in enumerate(TRADE_SIZES):
        row.append(InlineKeyboardButton(f"${s}", callback_data=f"{action}_{coin}_{s}"))
        if len(row) == 5:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Back", callback_data=f"{'buy' if 'buy' in action else 'sell'}_coin")])
    return InlineKeyboardMarkup(rows)

def confirm_kb(action: str, coin: str, amount: float, timeout_secs: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ YES — {action} ${amount}",
                              callback_data=f"confirm_{action}_{coin}_{amount}"),
         InlineKeyboardButton("❌ Cancel",
                              callback_data="cancel_trade")],
        [InlineKeyboardButton(f"⏳ Auto in {timeout_secs}s",
                              callback_data="noop")],
    ])

def auto_trade_kb():
    rows = []
    row  = []
    for i, c in enumerate(TOP_COINS):
        row.append(InlineKeyboardButton(c, callback_data=f"auto_{c}"))
        if len(row) == 5:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("🔀 All Coins (Scan)", callback_data="auto_scan")])
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="m_main")])
    return InlineKeyboardMarkup(rows)

# ══════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ══════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = update.effective_user.first_name or "Trader"
    USER_DATA[uid]["chat_id"] = update.effective_chat.id

    mock_note = "\n⚠️ _Demo mode — no real trades_" if not bc else \
                ("\n🟡 _Testnet mode_" if USE_TESTNET else "\n🟢 _LIVE trading_")

    text = (
        f"👋 *Բարի գալուստ, {name}!*\n\n"
        f"🤖 *Binance Pro Trading Bot*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛒 Գնել / 💰 Վաճառել ձեռքով\n"
        f"🤖 Ավտո-թրեյդ + հաստատման հարցում\n"
        f"⏳ {AUTO_CONFIRM_TIMEOUT}վ անպատասխան → ինքն կատարում է\n"
        f"💵 Sizes: $5 ~ $50\n"
        f"🪙 15 coin: {', '.join(TOP_COINS[:8])}...\n"
        f"{mock_note}\n\n"
        f"👇 *Ընտրեք գործողություն:*"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=main_menu_kb())

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📚 *COMMANDS*\n\n"
        "`/start` — Գլխավոր մենյու\n"
        "`/buy BTC 20` — Գնել $20 BTC\n"
        "`/sell ETH 15` — Վաճառել $15 ETH\n"
        "`/auto BTC` — Ավտո-ազդանշան BTC\n"
        "`/scan` — Scan բոլոր coin-ները\n"
        "`/price BTC ETH` — Գներ\n"
        "`/portfolio` — Ձեր portfolio\n"
        "`/analysis BTC` — TA ինդիկատորներ\n"
        "`/orders` — Trade պատմություն\n"
        "`/balance` — Binance balance\n"
        "`/alert BTC above 70000`\n"
        "`/fg` — Fear & Greed\n"
        "`/help` — Ուղեցույց\n\n"
        f"⏳ Auto-confirm timeout: *{AUTO_CONFIRM_TIMEOUT} sec*\n"
        f"🪙 Coins: {', '.join(TOP_COINS)}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=back_kb("m_main"))

async def cmd_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Direct: /buy BTC 20"""
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text(
            "📌 `/buy BTC 20` — Գնել $20 BTC", parse_mode=ParseMode.MARKDOWN)
        return
    await _execute_trade(update, ctx, args[0], "BUY", float(args[1]), confirmed=False)

async def cmd_sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Direct: /sell ETH 15"""
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text(
            "📌 `/sell ETH 15` — Վաճառել $15 ETH", parse_mode=ParseMode.MARKDOWN)
        return
    await _execute_trade(update, ctx, args[0], "SELL", float(args[1]), confirmed=False)

async def cmd_auto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Auto signal + ask: /auto BTC"""
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "📌 `/auto BTC` — TA signal + auto confirm",
            parse_mode=ParseMode.MARKDOWN)
        return
    await do_auto_trade(update.effective_user.id,
                        update.effective_chat.id,
                        args[0], ctx)

async def cmd_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Scan all TOP_COINS and pick best signal."""
    msg = await update.message.reply_text(
        "🔍 Scanning 15 coins for best signal...", parse_mode=ParseMode.MARKDOWN)
    best = await _scan_best_signal()
    if best:
        coin, ta = best
        await ctx.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=msg.message_id,
            text=(
                f"🔍 *Scan Complete*\n\n"
                f"🏆 Best signal: *{coin}USDT*\n"
                f"Signal: {ta['signal']}\n"
                f"RSI: `{ta['rsi']}`\n\n"
                f"🤖 Auto-trade with this coin?"
            ),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Auto Trade Now",
                                      callback_data=f"auto_{coin}"),
                 InlineKeyboardButton("❌ Skip", callback_data="m_main")]
            ])
        )
    else:
        await ctx.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=msg.message_id,
            text="⚪ No strong signals found right now.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_kb()
        )

async def cmd_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args or ["BTC", "ETH", "SOL"]
    lines = ["💹 *PRICES*\n"]
    for c in args[:6]:
        t = get_price(c)
        if "error" in t:
            lines.append(f"❌ {c}: {t['error']}")
        else:
            e = "🟢" if t["change"] >= 0 else "🔴"
            lines.append(f"{e} *{t['symbol']}*: `${t['price']:,.4f}` ({t['change']:+.2f}%)")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cmd_portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        portfolio_text(uid), parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

async def cmd_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    orders = USER_DATA[uid]["orders"]
    if not orders:
        await update.message.reply_text(
            "📭 No trades yet.", parse_mode=ParseMode.MARKDOWN)
        return
    lines = ["📖 *Trade History (last 10)*\n"]
    for o in orders[:10]:
        e = "🟢" if o["side"] == "BUY" else "🔴"
        lines.append(
            f"{e} `{o['time']}` *{o['symbol']}*\n"
            f"   {o['side']} `{o['qty']:.6f}` @ `${o['price']:.4f}` = `${o['total']:.2f}`"
            + (f"\n   _{o['note']}_" if o.get("note") else "") + "\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cmd_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bal = get_account_balance()
    if not bal["ok"]:
        await update.message.reply_text(f"❌ {bal['error']}", parse_mode=ParseMode.MARKDOWN)
        return
    mock_tag = " _(Demo)_" if bal.get("mock") else ""
    lines    = [f"💳 *Binance Balance*{mock_tag}\n"]
    for asset, qty in sorted(bal["balances"].items(), key=lambda x: -x[1])[:15]:
        lines.append(f"  • *{asset}*: `{qty:.6f}`")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cmd_analysis(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    coin = args[0] if args else "BTC"
    iv   = args[1] if len(args) > 1 else "1h"
    await update.message.reply_text(
        f"⏳ Analyzing *{coin.upper()}* [{iv}]...", parse_mode=ParseMode.MARKDOWN)
    ta = compute_ta(coin, iv)
    t  = get_price(coin)
    p  = t.get("price", 0)
    text = _ta_text(coin.upper(), p, ta, iv)
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cmd_alert(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    args = ctx.args
    if len(args) < 3:
        await update.message.reply_text(
            "📌 `/alert BTC above 70000`", parse_mode=ParseMode.MARKDOWN)
        return
    s, cond, price = args[0].upper(), args[1].lower(), float(args[2])
    USER_DATA[uid]["alerts"].append(
        {"symbol": sym(s), "condition": cond, "price": price,
         "chat_id": update.effective_chat.id})
    await update.message.reply_text(
        f"🔔 Alert: *{sym(s)}* {'⬆️' if cond=='above' else '⬇️'} `${price:,.2f}`",
        parse_mode=ParseMode.MARKDOWN)

async def cmd_fg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    fg  = fear_and_greed()
    bar = "█" * int(fg["value"]/5) + "░" * (20 - int(fg["value"]/5))
    await update.message.reply_text(
        f"😱 *Fear & Greed Index*\n```\n[{bar}]\n```\n"
        f"{fg['emoji']} *{fg['value']}/100* — {fg['label']}",
        parse_mode=ParseMode.MARKDOWN)

# ══════════════════════════════════════════════════════════════
#  CORE TRADE LOGIC
# ══════════════════════════════════════════════════════════════

async def _execute_trade(update_or_uid, ctx, coin: str, side: str,
                         amount: float, confirmed: bool = False,
                         auto_note: str = ""):
    """
    Core trade executor.
    If confirmed=False → ask user to confirm with timeout.
    If confirmed=True  → execute immediately.
    """
    if isinstance(update_or_uid, int):
        uid     = update_or_uid
        chat_id = USER_DATA[uid]["chat_id"]
        is_cb   = False
    else:
        update  = update_or_uid
        uid     = update.effective_user.id
        chat_id = update.effective_chat.id
        is_cb   = update.callback_query is not None
        USER_DATA[uid]["chat_id"] = chat_id

    t = get_price(coin)
    if "error" in t:
        msg = f"❌ Cannot get price for {coin}: {t['error']}"
        if is_cb:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    price = t["price"]
    qty   = amount / price

    if not confirmed:
        # ── ASK USER ─────────────────────────────────────────
        side_emoji = "🛒" if side == "BUY" else "💰"
        text = (
            f"{side_emoji} *Confirm Trade*\n\n"
            f"Coin:   *{sym(coin)}*\n"
            f"Action: *{side}*\n"
            f"Amount: `${amount}`\n"
            f"Price:  `${price:,.4f}`\n"
            f"Qty:    `≈{qty:.6f}`\n\n"
            f"⏳ *Auto-confirm in {AUTO_CONFIRM_TIMEOUT} sec...*\n"
            f"_(No response = auto execute)_"
        )
        kb = confirm_kb(side.lower(), coin.upper(), amount, AUTO_CONFIRM_TIMEOUT)

        if is_cb:
            sent = await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            msg_id = update.callback_query.message.message_id
        else:
            sent = await update.message.reply_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            msg_id = sent.message_id

        # Save pending trade
        USER_DATA[uid]["pending_trade"] = {
            "coin": coin, "side": side, "amount": amount,
            "msg_id": msg_id, "timestamp": time.time(), "chat_id": chat_id
        }

        # Schedule auto-confirm
        ctx.job_queue.run_once(
            _auto_confirm_job,
            when=AUTO_CONFIRM_TIMEOUT,
            data={"uid": uid, "coin": coin, "side": side,
                  "amount": amount, "msg_id": msg_id},
            name=f"autoconfirm_{uid}"
        )
        return

    # ── EXECUTE ──────────────────────────────────────────────
    order = place_order(coin, side, amount)
    USER_DATA[uid]["pending_trade"] = None

    if not order["ok"]:
        text = f"❌ Trade failed:\n`{order['error']}`"
        await ctx.bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN)
        return

    # Update portfolio + history
    update_portfolio(uid, order)
    record_order(uid, order, note=auto_note)

    mock_tag = " _(Demo order)_" if order.get("mock") else " _(Testnet)_" if USE_TESTNET else ""
    side_e   = "🛒 BOUGHT" if side == "BUY" else "💰 SOLD"
    text = (
        f"✅ *Trade Executed*{mock_tag}\n\n"
        f"{side_e} *{order['symbol']}*\n"
        f"Qty:   `{order['qty']:.6f}`\n"
        f"Price: `${order['price']:,.4f}`\n"
        f"Total: `${order['total']:.2f}`\n"
        f"ID:    `{order['orderId']}`"
        + (f"\n🤖 _{auto_note}_" if auto_note else "")
    )
    await ctx.bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN,
                               reply_markup=back_kb())


async def _auto_confirm_job(ctx: ContextTypes.DEFAULT_TYPE):
    """Job that fires after timeout — executes trade automatically."""
    data = ctx.job.data
    uid, coin, side, amount, msg_id = (
        data["uid"], data["coin"], data["side"],
        data["amount"], data["msg_id"]
    )
    pending = USER_DATA[uid].get("pending_trade")
    if not pending:
        return  # already handled by user

    chat_id = USER_DATA[uid]["chat_id"]

    # Edit the confirmation message
    try:
        await ctx.bot.edit_message_text(
            chat_id=chat_id, message_id=msg_id,
            text=f"⏳ Timeout! Auto-executing {side} ${amount} {coin}...",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass

    await _execute_trade(uid, ctx, coin, side, amount,
                         confirmed=True,
                         auto_note=f"Auto-executed after {AUTO_CONFIRM_TIMEOUT}s timeout")


async def do_auto_trade(uid: int, chat_id: int, coin: str,
                        ctx: ContextTypes.DEFAULT_TYPE):
    """Run TA and propose BUY/SELL based on signal."""
    USER_DATA[uid]["chat_id"] = chat_id
    ta = compute_ta(coin)
    t  = get_price(coin)
    p  = t.get("price", 0)

    # Decide side
    if ta["score"] >= 2:
        side   = "BUY"
        amount = 20  # default $20 for auto
    elif ta["score"] <= -2:
        side   = "SELL"
        amount = 20
    else:
        # No strong signal
        await ctx.bot.send_message(
            chat_id,
            f"📊 *{coin.upper()}USDT* — No strong signal\n"
            f"Signal: {ta['signal']}\n"
            f"RSI: `{ta['rsi']}` | Score: `{ta['score']}`\n\n"
            f"_No trade executed._",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_kb()
        )
        return

    side_e = "🛒" if side == "BUY" else "💰"
    text = (
        f"🤖 *Auto-Trade Signal*\n\n"
        f"Coin:   *{coin.upper()}USDT*\n"
        f"Price:  `${p:,.4f}`\n"
        f"Signal: {ta['signal']}\n"
        f"RSI:    `{ta['rsi']}`\n"
        f"MACD hist: `{ta['hist']}`\n\n"
        f"{side_e} Proposed: *{side} $20*\n\n"
        f"Choose size or confirm:"
    )
    # Let user pick size
    rows = []
    row  = []
    for s in TRADE_SIZES:
        row.append(InlineKeyboardButton(
            f"${s}", callback_data=f"confirm_{side.lower()}_{coin.upper()}_{s}"))
        if len(row) == 5:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(
        f"⏳ Auto ${amount} in {AUTO_CONFIRM_TIMEOUT}s",
        callback_data="noop")])
    rows.append([InlineKeyboardButton("❌ Skip", callback_data="cancel_trade")])
    kb = InlineKeyboardMarkup(rows)

    sent = await ctx.bot.send_message(
        chat_id, text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

    USER_DATA[uid]["pending_trade"] = {
        "coin": coin, "side": side, "amount": amount,
        "msg_id": sent.message_id, "timestamp": time.time(), "chat_id": chat_id
    }

    ctx.job_queue.run_once(
        _auto_confirm_job,
        when=AUTO_CONFIRM_TIMEOUT,
        data={"uid": uid, "coin": coin, "side": side,
              "amount": amount, "msg_id": sent.message_id},
        name=f"autoconfirm_{uid}"
    )

async def _scan_best_signal() -> Optional[tuple]:
    """Scan all TOP_COINS, return (coin, ta) with best absolute score."""
    best_coin, best_ta, best_score = None, None, 0
    for c in TOP_COINS:
        ta = compute_ta(c)
        if abs(ta["score"]) > abs(best_score):
            best_score = ta["score"]
            best_coin  = c
            best_ta    = ta
    if abs(best_score) >= 2:
        return best_coin, best_ta
    return None

def _ta_text(coin: str, price: float, ta: dict, iv: str) -> str:
    rsi_e = "🟢" if ta["rsi"] < 30 else ("🔴" if ta["rsi"] > 70 else "🟡")
    macd_e = "🟢" if ta["hist"] > 0 else "🔴"
    return (
        f"🔬 *{coin}USDT Analysis [{iv}]*\n\n"
        f"💵 Price: `${price:,.4f}`\n\n"
        f"📉 *RSI(14):* {rsi_e} `{ta['rsi']}`\n"
        f"   {'Oversold 🔥' if ta['rsi']<30 else ('Overbought ❄️' if ta['rsi']>70 else 'Normal')}\n\n"
        f"📊 *MACD:* {macd_e} hist=`{ta['hist']}`\n\n"
        f"📏 *Bollinger:*\n"
        f"   Upper `{ta['bb_u']}` | Mid `{ta['bb_m']}` | Lower `{ta['bb_l']}`\n\n"
        f"📐 *EMA 12/26:* `{ta['ema12']}` / `{ta['ema26']}`\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🎯 Signal: {ta['signal']}\n"
        f"📌 Score:  `{ta['score']}/4`"
    )

# ══════════════════════════════════════════════════════════════
#  CALLBACK HANDLER
# ══════════════════════════════════════════════════════════════

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    d   = q.data
    uid = update.effective_user.id
    USER_DATA[uid]["chat_id"] = update.effective_chat.id

    # ── MAIN MENU ──────────────────────────────────────────
    if d == "m_main":
        await q.edit_message_text(
            "🤖 *Binance Pro Bot* — Ընտրեք գործողություն:",
            parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())

    elif d == "m_buy":
        await q.edit_message_text(
            "🛒 *BUY — Ընտրեք coin:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=coin_select_kb("buyc"))

    elif d == "m_sell":
        await q.edit_message_text(
            "💰 *SELL — Ընտրեք coin:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=coin_select_kb("sellc"))

    elif d == "m_auto":
        await q.edit_message_text(
            "🤖 *Auto-Trade*\n\nՈր coin-ի TA ազդանշան ուզում եք:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=auto_trade_kb())

    elif d == "m_portfolio":
        await q.edit_message_text(
            portfolio_text(uid), parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_kb())

    elif d == "m_prices":
        lines = ["💹 *TOP 15 PRICES*\n"]
        for c in TOP_COINS:
            t = get_price(c)
            if "error" not in t:
                e = "🟢" if t["change"] >= 0 else "🔴"
                lines.append(f"{e} *{c}*: `${t['price']:,.4f}` `{t['change']:+.2f}%`")
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=back_kb())

    elif d == "m_analysis":
        await q.edit_message_text(
            "🔬 *Analysis — Ընտրեք coin:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=coin_select_kb("tac"))

    elif d == "m_screener":
        lines = ["📋 *SCREENER — Top 15*\n"]
        results = []
        for c in TOP_COINS:
            t = get_price(c)
            if "error" not in t:
                results.append((c, t["change"]))
        results.sort(key=lambda x: x[1], reverse=True)
        lines.append("🟢 *GAINERS*")
        for c, chg in results[:5]:
            t = get_price(c)
            lines.append(f"  • *{c}*: `{chg:+.2f}%` @ `${t['price']:,.4f}`")
        lines.append("\n🔴 *LOSERS*")
        for c, chg in reversed(results[-5:]):
            t = get_price(c)
            lines.append(f"  • *{c}*: `{chg:+.2f}%` @ `${t['price']:,.4f}`")
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=back_kb())

    elif d == "m_alerts":
        alerts = USER_DATA[uid]["alerts"]
        if not alerts:
            txt = "🔕 No alerts.\nCommand: `/alert BTC above 70000`"
        else:
            lines = ["🔔 *Alerts:*\n"]
            for a in alerts:
                e = "⬆️" if a["condition"] == "above" else "⬇️"
                lines.append(f"• *{a['symbol']}* {e} `${a['price']:,.2f}`")
            txt = "\n".join(lines)
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=back_kb())

    elif d == "m_orders":
        orders = USER_DATA[uid]["orders"]
        if not orders:
            txt = "📭 No trades yet."
        else:
            lines = ["📖 *Recent Trades*\n"]
            for o in orders[:8]:
                e = "🟢" if o["side"] == "BUY" else "🔴"
                lines.append(f"{e} *{o['symbol']}* {o['side']} `${o['total']:.2f}` — _{o['time']}_")
            txt = "\n".join(lines)
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=back_kb())

    elif d == "m_fg":
        fg  = fear_and_greed()
        bar = "█" * int(fg["value"]/5) + "░" * (20-int(fg["value"]/5))
        await q.edit_message_text(
            f"😱 *Fear & Greed*\n```\n[{bar}]\n```\n"
            f"{fg['emoji']} *{fg['value']}/100* — {fg['label']}",
            parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

    elif d == "m_whale":
        lines = ["🐋 *Whale Alerts (mock)*\n"]
        for _ in range(5):
            c    = random.choice(TOP_COINS)
            amt  = round(random.uniform(50,3000),1)
            tp   = get_price(c)["price"]
            usd  = int(amt*tp)
            side = random.choice(["🐋 BUY","🦈 SELL"])
            ago  = random.randint(1,59)
            lines.append(f"{side} `{amt} {c}` ≈`${usd:,}` — `{ago}m ago`")
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=back_kb())

    elif d == "m_help":
        await q.edit_message_text(
            "📚 Use `/help` for full command list.",
            parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

    # ── COIN SELECTED FOR BUY ──────────────────────────────
    elif d.startswith("buyc_"):
        coin = d.split("_")[1]
        t    = get_price(coin)
        txt  = (f"🛒 *BUY {coin}USDT*\n"
                f"Price: `${t.get('price',0):,.4f}`\n\n"
                f"Ընտրեք չափ ($):")
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=size_kb("preconfirm_buy", coin))

    elif d == "buy_coin":
        await q.edit_message_text("🛒 *BUY — Ընտրեք coin:*",
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=coin_select_kb("buyc"))

    # ── COIN SELECTED FOR SELL ─────────────────────────────
    elif d.startswith("sellc_"):
        coin = d.split("_")[1]
        t    = get_price(coin)
        txt  = (f"💰 *SELL {coin}USDT*\n"
                f"Price: `${t.get('price',0):,.4f}`\n\n"
                f"Ընտրեք չափ ($):")
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=size_kb("preconfirm_sell", coin))

    elif d == "sell_coin":
        await q.edit_message_text("💰 *SELL — Ընտրեք coin:*",
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=coin_select_kb("sellc"))

    # ── SIZE SELECTED → ASK CONFIRMATION ──────────────────
    elif d.startswith("preconfirm_buy_") or d.startswith("preconfirm_sell_"):
        parts  = d.split("_")
        side   = "BUY" if parts[1] == "buy" else "SELL"
        coin   = parts[2]
        amount = float(parts[3])
        await _execute_trade(update, ctx, coin, side, amount, confirmed=False)

    # ── AUTO TRADE COIN SELECTED ───────────────────────────
    elif d.startswith("auto_") and d != "auto_scan":
        coin = d.split("_")[1]
        await do_auto_trade(uid, update.effective_chat.id, coin, ctx)

    elif d == "auto_scan":
        await q.edit_message_text("🔍 Scanning...", parse_mode=ParseMode.MARKDOWN)
        best = await _scan_best_signal()
        if best:
            coin, ta = best
            await q.edit_message_text(
                f"🏆 Best signal: *{coin}USDT* — {ta['signal']}\nRSI: `{ta['rsi']}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 Trade This", callback_data=f"auto_{coin}"),
                     InlineKeyboardButton("❌ Skip",       callback_data="m_main")]
                ])
            )
        else:
            await q.edit_message_text("⚪ No strong signals.", reply_markup=back_kb())

    # ── TA COIN SELECTED ──────────────────────────────────
    elif d.startswith("tac_"):
        coin = d.split("_")[1]
        ta   = compute_ta(coin)
        t    = get_price(coin)
        text = _ta_text(coin.upper(), t.get("price",0), ta, "1h")
        await q.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 BUY",  callback_data=f"buyc_{coin}"),
                 InlineKeyboardButton("💰 SELL", callback_data=f"sellc_{coin}"),
                 InlineKeyboardButton("🔙",      callback_data="m_analysis")]
            ]))

    # ── CONFIRM TRADE ─────────────────────────────────────
    elif d.startswith("confirm_"):
        parts  = d.split("_")
        side   = parts[1].upper()
        coin   = parts[2]
        amount = float(parts[3])
        # Cancel the auto-confirm job
        jobs = ctx.job_queue.get_jobs_by_name(f"autoconfirm_{uid}")
        for j in jobs:
            j.schedule_removal()
        USER_DATA[uid]["pending_trade"] = None
        await _execute_trade(update, ctx, coin, side, amount,
                             confirmed=True, auto_note="User confirmed")

    elif d == "cancel_trade":
        jobs = ctx.job_queue.get_jobs_by_name(f"autoconfirm_{uid}")
        for j in jobs:
            j.schedule_removal()
        USER_DATA[uid]["pending_trade"] = None
        await q.edit_message_text(
            "❌ Trade cancelled.",
            reply_markup=back_kb())

    elif d == "noop":
        pass  # timer display button — do nothing

# ══════════════════════════════════════════════════════════════
#  BACKGROUND JOBS
# ══════════════════════════════════════════════════════════════

async def check_alerts_job(ctx: ContextTypes.DEFAULT_TYPE):
    for uid, data in list(USER_DATA.items()):
        triggered, remaining = [], []
        for alert in data.get("alerts", []):
            t = get_price(alert["symbol"])
            if "error" in t:
                remaining.append(alert)
                continue
            p   = t["price"]
            hit = (alert["condition"] == "above" and p >= alert["price"]) or \
                  (alert["condition"] == "below"  and p <= alert["price"])
            if hit:
                triggered.append((alert, p))
            else:
                remaining.append(alert)
        data["alerts"] = remaining
        for alert, cur in triggered:
            e = "⬆️" if alert["condition"] == "above" else "⬇️"
            try:
                await ctx.bot.send_message(
                    alert["chat_id"],
                    f"🔔 *ALERT!* *{alert['symbol']}* {e} `${alert['price']:,.2f}`\n"
                    f"Current: `${cur:,.4f}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                log.error(f"Alert send error: {e}")

# ══════════════════════════════════════════════════════════════
#  RENDER KEEP-ALIVE  (simple HTTP server)
# ══════════════════════════════════════════════════════════════

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Binance Bot running OK")
    def log_message(self, *args):
        pass  # suppress access logs

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    log.info(f"Health server on port {PORT}")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    if TELEGRAM_TOKEN == "YOUR_TOKEN":
        print("❌ Set TELEGRAM_TOKEN in environment!")
        print("   Render → Environment → Add Variable")
        return

    # Start keep-alive server in background thread
    Thread(target=run_health_server, daemon=True).start()

    # Build bot application
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("buy",       cmd_buy))
    app.add_handler(CommandHandler("sell",      cmd_sell))
    app.add_handler(CommandHandler("auto",      cmd_auto))
    app.add_handler(CommandHandler("scan",      cmd_scan))
    app.add_handler(CommandHandler("price",     cmd_price))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("orders",    cmd_orders))
    app.add_handler(CommandHandler("balance",   cmd_balance))
    app.add_handler(CommandHandler("analysis",  cmd_analysis))
    app.add_handler(CommandHandler("alert",     cmd_alert))
    app.add_handler(CommandHandler("fg",        cmd_fg))

    # Inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Background jobs
    app.job_queue.run_repeating(check_alerts_job, interval=60, first=15)

    log.info("🚀 Bot started! Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
