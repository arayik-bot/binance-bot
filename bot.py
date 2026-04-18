"""
╔══════════════════════════════════════════════════════════════════╗
║     BINANCE PRO TRADING BOT v3.0 — RUSSIAN UI + FULL FEATURES   ║
║  Spot + Futures + Margin | All Coins | Charts | Auto ON/OFF      ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import asyncio
import logging
import time
import math
import random
from datetime import datetime
from typing import Optional
from collections import defaultdict
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from telegram.constants import ParseMode

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
#  CONFIG
# ══════════════════════════════════════════════════════════════
TELEGRAM_TOKEN       = os.environ.get("TELEGRAM_TOKEN",  "YOUR_TOKEN")
BINANCE_API_KEY      = os.environ.get("BINANCE_API_KEY", "")
BINANCE_SECRET       = os.environ.get("BINANCE_SECRET",  "")
ADMIN_IDS            = list(map(int, os.environ.get("ADMIN_IDS", "0").split(",")))
USE_TESTNET          = os.environ.get("USE_TESTNET", "false").lower() == "true"
PORT                 = int(os.environ.get("PORT", 8080))
AUTO_CONFIRM_TIMEOUT = int(os.environ.get("AUTO_CONFIRM_TIMEOUT", "30"))

TRADE_SIZES = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]

TOP_COINS = [
    "BTC", "ETH", "BNB", "SOL", "XRP",
    "ADA", "DOGE", "AVAX", "DOT", "MATIC",
    "LINK", "LTC", "UNI", "ATOM", "NEAR"
]

# Trade types
TRADE_TYPES = {
    "spot":    "📈 Спот",
    "futures": "🔮 Фьючерсы",
    "margin":  "💳 Маржа",
}

# ══════════════════════════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════════════════════════
def default_user():
    return {
        "portfolio":      {},
        "alerts":         [],
        "orders":         [],
        "pending_trade":  None,
        "chat_id":        None,
        "auto_enabled":   False,       # auto-trade ON/OFF
        "auto_coins":     list(TOP_COINS),  # which coins to auto-trade
        "auto_type":      "spot",      # spot / futures / margin
        "auto_size":      20,          # default auto-trade size
        "waiting_custom_amount": None, # waiting for custom amount input
        "waiting_alert_coin":    None, # waiting for alert coin selection
    }

USER_DATA: dict = defaultdict(default_user)

# ══════════════════════════════════════════════════════════════
#  BINANCE CLIENT
# ══════════════════════════════════════════════════════════════
bc: Optional[object] = None
if BINANCE_OK and BINANCE_API_KEY:
    try:
        bc = Client(BINANCE_API_KEY, BINANCE_SECRET, testnet=USE_TESTNET)
        log.info("✅ Binance connected" + (" [TESTNET]" if USE_TESTNET else " [LIVE]"))
    except Exception as e:
        log.warning(f"Binance error: {e}")

# ══════════════════════════════════════════════════════════════
#  MOCK PRICES
# ══════════════════════════════════════════════════════════════
MOCK_PRICES = {
    "BTCUSDT": 67500, "ETHUSDT": 3450,  "BNBUSDT": 582,
    "SOLUSDT": 176,   "XRPUSDT": 0.58,  "ADAUSDT": 0.48,
    "DOGEUSDT": 0.162,"AVAXUSDT": 38.7, "DOTUSDT": 7.8,
    "MATICUSDT": 0.91,"LINKUSDT": 18.4, "LTCUSDT": 82.0,
    "UNIUSDT": 9.3,   "ATOMUSDT": 10.5, "NEARUSDT": 7.1,
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
                "high": float(t["highPrice"]), "low": float(t["lowPrice"]),
                "volume": float(t["volume"]),
            }
        except Exception as e:
            return {"error": str(e), "symbol": s}
    base = MOCK_PRICES.get(s, 10.0) * random.uniform(0.98, 1.02)
    chg  = round(random.uniform(-6, 6), 2)
    return {
        "symbol": s, "price": round(base, 6), "change": chg,
        "high": round(base*1.04, 6), "low": round(base*0.96, 6),
        "volume": round(random.uniform(5000, 500000), 2),
    }

def get_klines(coin: str, interval="1h", limit=60) -> list:
    s = sym(coin)
    if bc:
        try:
            return bc.get_klines(symbol=s, interval=interval, limit=limit)
        except:
            pass
    base = MOCK_PRICES.get(s, 50.0)
    data = []
    t = int(time.time()*1000) - limit*3600000
    for _ in range(limit):
        o  = base * random.uniform(0.99, 1.01)
        h  = o * random.uniform(1.00, 1.02)
        lo = o * random.uniform(0.98, 1.00)
        c  = random.uniform(lo, h)
        base = c
        data.append([t, str(o), str(h), str(lo), str(c),
                      str(random.uniform(100,5000)), t+3600000])
        t += 3600000
    return data

def get_account_balance() -> dict:
    if bc:
        try:
            acc = bc.get_account()
            bals = {b["asset"]: float(b["free"])
                    for b in acc["balances"] if float(b["free"]) > 0}
            return {"ok": True, "balances": bals, "usdt": bals.get("USDT", 0)}
        except Exception as e:
            return {"ok": False, "error": str(e), "usdt": 0}
    return {"ok": True,
            "balances": {"USDT": 1000.0, "BTC": 0.01, "ETH": 0.5},
            "usdt": 1000.0, "mock": True}

def place_order(coin: str, side: str, usdt_amount: float,
                trade_type: str = "spot") -> dict:
    s      = sym(coin)
    ticker = get_price(coin)
    if "error" in ticker:
        return {"ok": False, "error": ticker["error"]}
    price = ticker["price"]
    qty   = usdt_amount / price

    if bc:
        try:
            if trade_type == "futures":
                # Futures market order
                if side == "BUY":
                    order = bc.futures_create_order(
                        symbol=s, side="BUY", type="MARKET",
                        quoteOrderQty=usdt_amount)
                else:
                    order = bc.futures_create_order(
                        symbol=s, side="SELL", type="MARKET",
                        quantity=f"{qty:.6f}")
            elif trade_type == "margin":
                # Margin market order
                if side == "BUY":
                    order = bc.create_margin_order(
                        symbol=s, side="BUY", type="MARKET",
                        quoteOrderQty=usdt_amount)
                else:
                    order = bc.create_margin_order(
                        symbol=s, side="SELL", type="MARKET",
                        quantity=f"{qty:.6f}")
            else:
                # Spot
                if side == "BUY":
                    order = bc.order_market_buy(symbol=s, quoteOrderQty=usdt_amount)
                else:
                    order = bc.order_market_sell(symbol=s, quantity=f"{qty:.6f}")

            fills = order.get("fills", [{}])
            fp = float(fills[0].get("price", price)) if fills else price
            fq = float(order.get("executedQty", qty))
            return {"ok": True, "symbol": s, "side": side,
                    "qty": fq, "price": fp, "total": fq*fp,
                    "orderId": order.get("orderId"),
                    "type": trade_type, "mock": False}
        except BinanceAPIException as e:
            return {"ok": False, "error": f"Binance: {e.message}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    ep = price * random.uniform(0.999, 1.001)
    eq = usdt_amount / ep
    return {"ok": True, "symbol": s, "side": side,
            "qty": round(eq, 8), "price": round(ep, 4),
            "total": round(usdt_amount, 2),
            "orderId": f"MOCK-{int(time.time())}",
            "type": trade_type, "mock": True}

# ══════════════════════════════════════════════════════════════
#  ASCII CHART
# ══════════════════════════════════════════════════════════════
def ascii_chart(coin: str, interval="1h", bars=40) -> str:
    klines = get_klines(coin, interval, bars)
    closes = [float(k[4]) for k in klines]
    opens  = [float(k[1]) for k in klines]
    hi_all = max(float(k[2]) for k in klines)
    lo_all = min(float(k[3]) for k in klines)
    rows   = 10
    result = []

    for row in range(rows, -1, -1):
        level    = lo_all + (hi_all - lo_all) * row / rows
        price_lb = f"{level:>10.2f} │"
        line     = ""
        for i, (c, o) in enumerate(zip(closes, opens)):
            if abs(c - level) < (hi_all - lo_all) / rows / 2:
                line += "▓" if c >= o else "░"
            else:
                line += " "
        result.append(price_lb + line)

    result.append(" " * 11 + "└" + "─" * bars)
    # Last price arrow
    last = closes[-1]
    chg  = ((last - closes[0]) / closes[0] * 100) if closes[0] else 0
    result.append(f"           Last: ${last:,.4f}  ({chg:+.2f}%)")
    return "\n".join(result)

# ══════════════════════════════════════════════════════════════
#  TECHNICAL ANALYSIS
# ══════════════════════════════════════════════════════════════
def compute_ta(coin: str, interval="1h") -> dict:
    klines = get_klines(coin, interval, 120)
    closes = [float(k[4]) for k in klines]

    def ema(prices, p):
        k = 2/(p+1); res = [sum(prices[:p])/p]
        for x in prices[p:]: res.append(x*k + res[-1]*(1-k))
        return res

    def rsi(prices, p=14):
        g, lo = [], []
        for i in range(1, len(prices)):
            d = prices[i]-prices[i-1]
            g.append(max(d,0)); lo.append(max(-d,0))
        ag = sum(g[-p:])/p; al = sum(lo[-p:])/p
        if al == 0: return 100.0
        return round(100 - 100/(1+ag/al), 2)

    e12 = ema(closes,12); e26 = ema(closes,26)
    n   = min(len(e12), len(e26))
    ml  = [e12[-n+i]-e26[i] for i in range(n)]
    se  = ema(ml, 9)
    hist = ml[-1]-se[-1]

    p20 = closes[-20:]; sma20 = sum(p20)/20
    std = math.sqrt(sum((c-sma20)**2 for c in p20)/20)
    bb_u = sma20+2*std; bb_l = sma20-2*std

    rsi_v = rsi(closes); cur = closes[-1]
    score = 0
    if rsi_v < 30:      score += 2
    elif rsi_v > 70:    score -= 2
    if hist > 0:        score += 1
    else:               score -= 1
    if cur < bb_l:      score += 1
    elif cur > bb_u:    score -= 1
    if e12[-1]>e26[-1]: score += 1
    else:               score -= 1

    if score >= 3:    sig = "🟢 СИЛЬНАЯ ПОКУПКА"
    elif score >= 1:  sig = "🟩 ПОКУПКА"
    elif score <= -3: sig = "🔴 СИЛЬНАЯ ПРОДАЖА"
    elif score <= -1: sig = "🟥 ПРОДАЖА"
    else:             sig = "🟡 НЕЙТРАЛЬНО"

    return {
        "rsi": rsi_v, "hist": round(hist,4), "signal": sig, "score": score,
        "bb_u": round(bb_u,4), "bb_l": round(bb_l,4), "bb_m": round(sma20,4),
        "ema12": round(e12[-1],4), "ema26": round(e26[-1],4),
        "macd": round(ml[-1],4),
    }

def fear_and_greed() -> dict:
    v = random.randint(18,88)
    if v<25:   lb,em="Крайний страх","😱"
    elif v<45: lb,em="Страх","😨"
    elif v<55: lb,em="Нейтрально","😐"
    elif v<75: lb,em="Жадность","😏"
    else:      lb,em="Крайняя жадность","🤑"
    return {"value":v,"label":lb,"emoji":em}

# ══════════════════════════════════════════════════════════════
#  PORTFOLIO
# ══════════════════════════════════════════════════════════════
def portfolio_text(uid: int) -> str:
    port = USER_DATA[uid]["portfolio"]
    if not port:
        return "📂 Портфель пуст.\nСначала совершите сделку."
    lines = ["💼 *ПОРТФЕЛЬ*\n"]
    ti = tc = 0.0
    for s, pos in port.items():
        t = get_price(s)
        if "error" in t: continue
        p=t["price"]; q=pos["qty"]; avg=pos["avg_price"]
        inv=q*avg; cur=q*p; pnl=cur-inv
        pct=pnl/inv*100 if inv else 0
        ti+=inv; tc+=cur
        e="🟢" if pnl>=0 else "🔴"
        lines.append(
            f"{e} *{s}*\n"
            f"   `{q:.6f}` @ avg `${avg:.4f}`\n"
            f"   Сейчас `${p:.4f}` | Стоимость `${cur:.2f}`\n"
            f"   PnL `{'+' if pnl>=0 else ''}{pnl:.2f}$` ({pct:+.1f}%)\n"
        )
    tp=tc-ti; te="🟢" if tp>=0 else "🔴"
    lines += [
        "─────────────────",
        f"💰 Вложено: `${ti:.2f}`",
        f"💎 Стоимость: `${tc:.2f}`",
        f"{te} PnL: `{'+' if tp>=0 else ''}{tp:.2f}$` ({(tp/ti*100 if ti else 0):+.1f}%)"
    ]
    return "\n".join(lines)

def update_portfolio(uid: int, order: dict):
    s=order["symbol"]; qty=order["qty"]; p=order["price"]
    port=USER_DATA[uid]["portfolio"]
    if order["side"]=="BUY":
        if s in port:
            oq=port[s]["qty"]; oa=port[s]["avg_price"]
            nq=oq+qty; na=(oq*oa+qty*p)/nq
            port[s]={"qty":nq,"avg_price":round(na,6)}
        else:
            port[s]={"qty":qty,"avg_price":p}
    else:
        if s in port:
            nq=port[s]["qty"]-qty
            if nq<=0.000001: del port[s]
            else: port[s]["qty"]=round(nq,8)

def record_order(uid:int, order:dict, note=""):
    entry={
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "symbol": order["symbol"], "side": order["side"],
        "qty": order["qty"], "price": order["price"],
        "total": order["total"], "orderId": order.get("orderId",""),
        "type": order.get("type","spot"), "note": note
    }
    USER_DATA[uid]["orders"].insert(0,entry)
    USER_DATA[uid]["orders"]=USER_DATA[uid]["orders"][:50]

# ══════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Купить",      callback_data="m_buy"),
         InlineKeyboardButton("💰 Продать",     callback_data="m_sell")],
        [InlineKeyboardButton("🤖 Авто-трейд",  callback_data="m_auto_menu"),
         InlineKeyboardButton("💼 Портфель",    callback_data="m_portfolio")],
        [InlineKeyboardButton("📊 Анализ",      callback_data="m_analysis"),
         InlineKeyboardButton("📉 График",      callback_data="m_chart")],
        [InlineKeyboardButton("💹 Цены",        callback_data="m_prices"),
         InlineKeyboardButton("📋 Скринер",     callback_data="m_screener")],
        [InlineKeyboardButton("🔔 Алерты",      callback_data="m_alerts_menu"),
         InlineKeyboardButton("📖 Сделки",      callback_data="m_orders")],
        [InlineKeyboardButton("😱 Страх/Жадн.", callback_data="m_fg"),
         InlineKeyboardButton("🐋 Киты",        callback_data="m_whale")],
        [InlineKeyboardButton("💳 Баланс",      callback_data="m_balance"),
         InlineKeyboardButton("ℹ️ Помощь",       callback_data="m_help")],
    ])

def back_kb(target="m_main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data=target)]])

def coin_kb(action: str, back: str = "m_main"):
    rows = []; row = []
    for c in TOP_COINS:
        row.append(InlineKeyboardButton(c, callback_data=f"{action}_{c}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data=back)])
    return InlineKeyboardMarkup(rows)

def size_kb(action: str, coin: str, back_action: str):
    rows = []; row = []
    for s in TRADE_SIZES:
        row.append(InlineKeyboardButton(f"${s}", callback_data=f"{action}_{coin}_{s}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(
        "✏️ Своя сумма", callback_data=f"custom_amount_{action}_{coin}")])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data=back_action)])
    return InlineKeyboardMarkup(rows)

def auto_menu_kb(uid: int):
    enabled = USER_DATA[uid]["auto_enabled"]
    atype   = USER_DATA[uid]["auto_type"]
    asize   = USER_DATA[uid]["auto_size"]
    status  = "🟢 ВКЛ" if enabled else "🔴 ВЫКЛ"
    toggle  = "⏹ Выключить" if enabled else "▶️ Включить"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Авто-трейд: {status}",
                              callback_data="auto_toggle")],
        [InlineKeyboardButton(toggle, callback_data="auto_toggle")],
        [InlineKeyboardButton(f"Тип: {TRADE_TYPES[atype]}",
                              callback_data="auto_type_menu")],
        [InlineKeyboardButton(f"Сумма: ${asize}",
                              callback_data="auto_size_menu")],
        [InlineKeyboardButton("🪙 Монеты для авто",
                              callback_data="auto_coins_menu")],
        [InlineKeyboardButton("🔍 Сканировать сейчас",
                              callback_data="auto_scan")],
        [InlineKeyboardButton("🔙 Назад", callback_data="m_main")],
    ])

def auto_type_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 Спот",      callback_data="set_atype_spot")],
        [InlineKeyboardButton("🔮 Фьючерсы", callback_data="set_atype_futures")],
        [InlineKeyboardButton("💳 Маржа",    callback_data="set_atype_margin")],
        [InlineKeyboardButton("🔙 Назад",    callback_data="m_auto_menu")],
    ])

def auto_size_kb(uid: int):
    rows=[]; row=[]
    for s in TRADE_SIZES:
        row.append(InlineKeyboardButton(f"${s}", callback_data=f"set_asize_{s}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(
        "✏️ Своя сумма", callback_data="set_asize_custom")])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="m_auto_menu")])
    return InlineKeyboardMarkup(rows)

def auto_coins_kb(uid: int):
    selected = USER_DATA[uid]["auto_coins"]
    rows=[]; row=[]
    for c in TOP_COINS:
        check = "✅" if c in selected else "◻️"
        row.append(InlineKeyboardButton(
            f"{check}{c}", callback_data=f"toggle_acoin_{c}"))
        if len(row)==3: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([
        InlineKeyboardButton("✅ Все",   callback_data="acoin_all"),
        InlineKeyboardButton("❌ Сброс", callback_data="acoin_none"),
    ])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="m_auto_menu")])
    return InlineKeyboardMarkup(rows)

def alert_coin_kb():
    rows=[]; row=[]
    for c in TOP_COINS:
        row.append(InlineKeyboardButton(c, callback_data=f"alert_coin_{c}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="m_alerts_menu")])
    return InlineKeyboardMarkup(rows)

def alert_condition_kb(coin: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⬆️ Выше (above)", callback_data=f"alert_cond_{coin}_above"),
         InlineKeyboardButton(f"⬇️ Ниже (below)", callback_data=f"alert_cond_{coin}_below")],
        [InlineKeyboardButton("🔙 Назад", callback_data="alert_add")],
    ])

def alerts_menu_kb(uid: int):
    alerts = USER_DATA[uid]["alerts"]
    rows = [
        [InlineKeyboardButton("➕ Добавить алерт", callback_data="alert_add")],
    ]
    if alerts:
        rows.append([InlineKeyboardButton(
            f"🗑 Удалить все ({len(alerts)})", callback_data="alert_clear")])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="m_main")])
    return InlineKeyboardMarkup(rows)

def chart_interval_kb(coin: str):
    intervals = ["15m","1h","4h","1d","1w"]
    rows=[row:=[]]
    for iv in intervals:
        row.append(InlineKeyboardButton(iv, callback_data=f"chart_{coin}_{iv}"))
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="m_chart")])
    return InlineKeyboardMarkup(rows)

def _ta_text(coin:str, price:float, ta:dict, iv:str) -> str:
    re = "🟢" if ta["rsi"]<30 else ("🔴" if ta["rsi"]>70 else "🟡")
    me = "🟢" if ta["hist"]>0 else "🔴"
    return (
        f"🔬 *Анализ {coin}USDT [{iv}]*\n\n"
        f"💵 Цена: `${price:,.4f}`\n\n"
        f"📉 *RSI(14):* {re} `{ta['rsi']}`\n"
        f"   {'Перепродан 🔥' if ta['rsi']<30 else ('Перекуплен ❄️' if ta['rsi']>70 else 'Норма')}\n\n"
        f"📊 *MACD:* {me} hist=`{ta['hist']}`\n\n"
        f"📏 *Bollinger:*\n"
        f"   Верх `{ta['bb_u']}` | Середина `{ta['bb_m']}` | Низ `{ta['bb_l']}`\n\n"
        f"📐 *EMA 12/26:* `{ta['ema12']}` / `{ta['ema26']}`\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🎯 Сигнал: {ta['signal']}\n"
        f"📌 Оценка: `{ta['score']}/4`"
    )

# ══════════════════════════════════════════════════════════════
#  CORE TRADE LOGIC
# ══════════════════════════════════════════════════════════════
async def _execute_trade(update_or_uid, ctx, coin:str, side:str,
                          amount:float, confirmed:bool=False,
                          trade_type:str="spot", auto_note:str=""):
    if isinstance(update_or_uid, int):
        uid=update_or_uid; chat_id=USER_DATA[uid]["chat_id"]
        is_cb=False; update=None
    else:
        update=update_or_uid; uid=update.effective_user.id
        chat_id=update.effective_chat.id
        is_cb=update.callback_query is not None
        USER_DATA[uid]["chat_id"]=chat_id

    t=get_price(coin)
    if "error" in t:
        msg=f"❌ Не удалось получить цену {coin}: {t['error']}"
        if is_cb: await update.callback_query.edit_message_text(msg)
        elif update: await update.message.reply_text(msg)
        return

    price=t["price"]; qty=amount/price
    type_label=TRADE_TYPES.get(trade_type,"📈 Спот")

    if not confirmed:
        se="🛒" if side=="BUY" else "💰"
        text=(
            f"{se} *Подтвердить сделку*\n\n"
            f"Монета:  *{sym(coin)}*\n"
            f"Действие: *{'КУПИТЬ' if side=='BUY' else 'ПРОДАТЬ'}*\n"
            f"Тип:     {type_label}\n"
            f"Сумма:   `${amount}`\n"
            f"Цена:    `${price:,.4f}`\n"
            f"Кол-во:  `~{qty:.6f}`\n\n"
            f"⏳ *Авто-подтверждение через {AUTO_CONFIRM_TIMEOUT} сек...*\n"
            f"_(Нет ответа = авто-исполнение)_"
        )
        rows=[
            [InlineKeyboardButton(
                f"✅ ДА — {'КУПИТЬ' if side=='BUY' else 'ПРОДАТЬ'} ${amount}",
                callback_data=f"confirm_{side.lower()}_{coin.upper()}_{amount}_{trade_type}"),
             InlineKeyboardButton("❌ Отмена", callback_data="cancel_trade")],
            [InlineKeyboardButton(f"⏳ Авто через {AUTO_CONFIRM_TIMEOUT}с",
                                  callback_data="noop")],
        ]
        kb=InlineKeyboardMarkup(rows)
        if is_cb:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            msg_id=update.callback_query.message.message_id
        else:
            sent=await update.message.reply_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            msg_id=sent.message_id

        USER_DATA[uid]["pending_trade"]={
            "coin":coin,"side":side,"amount":amount,
            "msg_id":msg_id,"timestamp":time.time(),
            "chat_id":chat_id,"trade_type":trade_type
        }
        ctx.job_queue.run_once(
            _auto_confirm_job, when=AUTO_CONFIRM_TIMEOUT,
            data={"uid":uid,"coin":coin,"side":side,"amount":amount,
                  "msg_id":msg_id,"trade_type":trade_type},
            name=f"autoconfirm_{uid}"
        )
        return

    order=place_order(coin, side, amount, trade_type)
    USER_DATA[uid]["pending_trade"]=None
    if not order["ok"]:
        await ctx.bot.send_message(
            chat_id, f"❌ Ошибка сделки:\n`{order['error']}`",
            parse_mode=ParseMode.MARKDOWN)
        return

    update_portfolio(uid, order)
    record_order(uid, order, note=auto_note)

    mock_tag=" _(Демо)_" if order.get("mock") else (" _(Testnet)_" if USE_TESTNET else "")
    se="🛒 КУПЛЕНО" if side=="BUY" else "💰 ПРОДАНО"
    type_label=TRADE_TYPES.get(order.get("type","spot"),"📈 Спот")
    text=(
        f"✅ *Сделка исполнена*{mock_tag}\n\n"
        f"{se} *{order['symbol']}*\n"
        f"Тип:    {type_label}\n"
        f"Кол-во: `{order['qty']:.6f}`\n"
        f"Цена:   `${order['price']:,.4f}`\n"
        f"Итого:  `${order['total']:.2f}`\n"
        f"ID:     `{order['orderId']}`"
        +(f"\n🤖 _{auto_note}_" if auto_note else "")
    )
    await ctx.bot.send_message(chat_id, text,
                               parse_mode=ParseMode.MARKDOWN,
                               reply_markup=back_kb())

async def _auto_confirm_job(ctx: ContextTypes.DEFAULT_TYPE):
    data=ctx.job.data
    uid=data["uid"]; coin=data["coin"]; side=data["side"]
    amount=data["amount"]; msg_id=data["msg_id"]
    trade_type=data.get("trade_type","spot")
    if not USER_DATA[uid].get("pending_trade"): return
    chat_id=USER_DATA[uid]["chat_id"]
    try:
        await ctx.bot.edit_message_text(
            chat_id=chat_id, message_id=msg_id,
            text=f"⏳ Таймаут! Авто-исполнение {side} ${amount} {coin}...",
            parse_mode=ParseMode.MARKDOWN)
    except: pass
    await _execute_trade(uid, ctx, coin, side, amount,
                         confirmed=True, trade_type=trade_type,
                         auto_note=f"Авто через {AUTO_CONFIRM_TIMEOUT}с")

async def do_auto_trade(uid:int, chat_id:int, coin:str,
                        ctx:ContextTypes.DEFAULT_TYPE):
    if not USER_DATA[uid]["auto_enabled"]: return
    USER_DATA[uid]["chat_id"]=chat_id
    ta=compute_ta(coin); t=get_price(coin); p=t.get("price",0)
    trade_type=USER_DATA[uid]["auto_type"]
    amount=USER_DATA[uid]["auto_size"]

    if ta["score"]>=2: side="BUY"
    elif ta["score"]<=-2: side="SELL"
    else: return  # no signal, skip silently

    se="🛒" if side=="BUY" else "💰"
    type_label=TRADE_TYPES.get(trade_type,"📈 Спот")
    text=(
        f"🤖 *Авто-Трейд Сигнал*\n\n"
        f"Монета:  *{coin.upper()}USDT*\n"
        f"Тип:     {type_label}\n"
        f"Цена:    `${p:,.4f}`\n"
        f"Сигнал:  {ta['signal']}\n"
        f"RSI:     `{ta['rsi']}`\n"
        f"MACD:    `{ta['hist']}`\n\n"
        f"{se} Предложение: *{'КУПИТЬ' if side=='BUY' else 'ПРОДАТЬ'}*\n\n"
        f"Выберите сумму или подождите {AUTO_CONFIRM_TIMEOUT}с:"
    )
    rows=[]; row=[]
    for s in TRADE_SIZES:
        row.append(InlineKeyboardButton(
            f"${s}", callback_data=f"confirm_{side.lower()}_{coin.upper()}_{s}_{trade_type}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(
        "✏️ Своя сумма",
        callback_data=f"custom_amount_confirm_{side.lower()}_{coin.upper()}_{trade_type}")])
    rows.append([InlineKeyboardButton(
        f"⏳ Авто ${amount} через {AUTO_CONFIRM_TIMEOUT}с", callback_data="noop")])
    rows.append([InlineKeyboardButton("❌ Пропустить", callback_data="cancel_trade")])

    sent=await ctx.bot.send_message(
        chat_id, text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(rows))
    USER_DATA[uid]["pending_trade"]={
        "coin":coin,"side":side,"amount":amount,
        "msg_id":sent.message_id,"timestamp":time.time(),
        "chat_id":chat_id,"trade_type":trade_type
    }
    ctx.job_queue.run_once(
        _auto_confirm_job, when=AUTO_CONFIRM_TIMEOUT,
        data={"uid":uid,"coin":coin,"side":side,"amount":amount,
              "msg_id":sent.message_id,"trade_type":trade_type},
        name=f"autoconfirm_{uid}"
    )

async def _scan_best(uid:int) -> Optional[tuple]:
    coins=USER_DATA[uid]["auto_coins"] or TOP_COINS
    best_coin=best_ta=None; best_score=0
    for c in coins:
        ta=compute_ta(c)
        if abs(ta["score"])>abs(best_score):
            best_score=ta["score"]; best_coin=c; best_ta=ta
    return (best_coin,best_ta) if abs(best_score)>=2 else None

# ══════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ══════════════════════════════════════════════════════════════
async def cmd_start(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    name=update.effective_user.first_name or "Трейдер"
    USER_DATA[uid]["chat_id"]=update.effective_chat.id
    live_tag="\n⚠️ _Демо-режим_" if not bc else \
             ("\n🟡 _Testnet_" if USE_TESTNET else "\n🟢 _LIVE торговля_")
    auto_st="🟢 ВКЛ" if USER_DATA[uid]["auto_enabled"] else "🔴 ВЫКЛ"
    await update.message.reply_text(
        f"👋 *Добро пожаловать, {name}!*\n\n"
        f"🤖 *Binance Pro Trading Bot*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛒 Покупка / 💰 Продажа вручную\n"
        f"📈 Спот | 🔮 Фьючерсы | 💳 Маржа\n"
        f"🤖 Авто-трейд: {auto_st}\n"
        f"⏳ Таймаут: {AUTO_CONFIRM_TIMEOUT}с → авто-исполнение\n"
        f"💵 Стандартные и свои суммы\n"
        f"🔔 Алерты по всем 15 монетам\n"
        f"📉 Графики ASCII\n"
        f"{live_tag}\n\n"
        f"👇 *Выберите действие:*",
        parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())

async def cmd_help(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 *КОМАНДЫ*\n\n"
        "`/start` — Главное меню\n"
        "`/buy BTC 20` — Купить $20 BTC\n"
        "`/sell ETH 15` — Продать $15 ETH\n"
        "`/auto on/off` — Вкл/выкл авто\n"
        "`/scan` — Сканировать монеты\n"
        "`/price BTC ETH` — Цены\n"
        "`/chart BTC 1h` — График\n"
        "`/portfolio` — Портфель + PnL\n"
        "`/analysis BTC` — TA индикаторы\n"
        "`/orders` — История сделок\n"
        "`/balance` — Баланс Binance\n"
        "`/alert BTC above 70000`\n"
        "`/fg` — Страх и Жадность\n\n"
        f"⏳ Авто-таймаут: *{AUTO_CONFIRM_TIMEOUT}с*\n"
        f"🪙 Монеты: {', '.join(TOP_COINS)}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

async def cmd_buy(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    args=ctx.args
    if len(args)<2:
        await update.message.reply_text("📌 `/buy BTC 20`", parse_mode=ParseMode.MARKDOWN)
        return
    uid=update.effective_user.id
    trade_type=USER_DATA[uid]["auto_type"]
    await _execute_trade(update, ctx, args[0], "BUY", float(args[1]),
                         confirmed=False, trade_type=trade_type)

async def cmd_sell(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    args=ctx.args
    if len(args)<2:
        await update.message.reply_text("📌 `/sell ETH 15`", parse_mode=ParseMode.MARKDOWN)
        return
    uid=update.effective_user.id
    trade_type=USER_DATA[uid]["auto_type"]
    await _execute_trade(update, ctx, args[0], "SELL", float(args[1]),
                         confirmed=False, trade_type=trade_type)

async def cmd_auto(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    args=ctx.args
    if args and args[0].lower() in ("on","off","вкл","выкл"):
        enable=(args[0].lower() in ("on","вкл"))
        USER_DATA[uid]["auto_enabled"]=enable
        st="🟢 ВКЛЮЧЁН" if enable else "🔴 ВЫКЛЮЧЕН"
        await update.message.reply_text(
            f"🤖 Авто-трейд: *{st}*", parse_mode=ParseMode.MARKDOWN)
        return
    await update.message.reply_text(
        f"🤖 *Авто-трейд меню:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=auto_menu_kb(uid))

async def cmd_scan(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    msg=await update.message.reply_text("🔍 Сканирование 15 монет...")
    best=await _scan_best(uid)
    if best:
        coin,ta=best
        await ctx.bot.edit_message_text(
            chat_id=update.effective_chat.id, message_id=msg.message_id,
            text=(f"🏆 Лучший сигнал: *{coin}USDT*\n"
                  f"Сигнал: {ta['signal']} | RSI: `{ta['rsi']}`\n\nАвто-трейд?"),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Торговать", callback_data=f"auto_do_{coin}"),
                 InlineKeyboardButton("❌ Пропустить", callback_data="m_main")]
            ]))
    else:
        await ctx.bot.edit_message_text(
            chat_id=update.effective_chat.id, message_id=msg.message_id,
            text="⚪ Нет сильных сигналов.", reply_markup=back_kb())

async def cmd_price(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    args=ctx.args or ["BTC","ETH","SOL"]
    lines=["💹 *ЦЕНЫ*\n"]
    for c in args[:6]:
        t=get_price(c)
        if "error" in t: lines.append(f"❌ {c}: {t['error']}")
        else:
            e="🟢" if t["change"]>=0 else "🔴"
            lines.append(f"{e} *{t['symbol']}*: `${t['price']:,.4f}` ({t['change']:+.2f}%)")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cmd_chart(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    args=ctx.args
    coin=args[0] if args else "BTC"
    iv=args[1] if len(args)>1 else "1h"
    msg=await update.message.reply_text(f"⏳ Генерация графика {coin.upper()} [{iv}]...")
    chart=ascii_chart(coin, iv)
    t=get_price(coin)
    await ctx.bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=msg.message_id,
        text=f"📉 *{coin.upper()}USDT* [{iv}]\n```\n{chart}\n```",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=chart_interval_kb(coin.upper()))

async def cmd_portfolio(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    await update.message.reply_text(
        portfolio_text(uid), parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

async def cmd_orders(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    orders=USER_DATA[uid]["orders"]
    if not orders:
        await update.message.reply_text("📭 Нет сделок."); return
    lines=["📖 *История сделок*\n"]
    for o in orders[:10]:
        e="🟢" if o["side"]=="BUY" else "🔴"
        tl=TRADE_TYPES.get(o.get("type","spot"),"")
        lines.append(
            f"{e} `{o['time']}` *{o['symbol']}* {tl}\n"
            f"   {o['side']} `{o['qty']:.6f}` @ `${o['price']:.4f}` = `${o['total']:.2f}`\n")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cmd_balance(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    bal=get_account_balance()
    if not bal["ok"]:
        await update.message.reply_text(f"❌ {bal['error']}"); return
    mt=" _(Демо)_" if bal.get("mock") else ""
    lines=[f"💳 *Баланс Binance*{mt}\n"]
    for asset,qty in sorted(bal["balances"].items(), key=lambda x:-x[1])[:15]:
        lines.append(f"  • *{asset}*: `{qty:.6f}`")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cmd_analysis(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    args=ctx.args; coin=args[0] if args else "BTC"; iv=args[1] if len(args)>1 else "1h"
    await update.message.reply_text(f"⏳ Анализ *{coin.upper()}* [{iv}]...",
                                    parse_mode=ParseMode.MARKDOWN)
    ta=compute_ta(coin,iv); t=get_price(coin)
    await update.message.reply_text(
        _ta_text(coin.upper(), t.get("price",0), ta, iv),
        parse_mode=ParseMode.MARKDOWN)

async def cmd_alert(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; args=ctx.args
    if len(args)<3:
        await update.message.reply_text(
            "📌 `/alert BTC above 70000`\n📌 `/alert ETH below 3000`",
            parse_mode=ParseMode.MARKDOWN); return
    s,cond,price=args[0].upper(),args[1].lower(),float(args[2])
    USER_DATA[uid]["alerts"].append(
        {"symbol":sym(s),"condition":cond,"price":price,
         "chat_id":update.effective_chat.id})
    await update.message.reply_text(
        f"🔔 Алерт: *{sym(s)}* {'⬆️' if cond=='above' else '⬇️'} `${price:,.2f}`",
        parse_mode=ParseMode.MARKDOWN)

async def cmd_fg(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    fg=fear_and_greed()
    bar="█"*int(fg["value"]/5)+"░"*(20-int(fg["value"]/5))
    await update.message.reply_text(
        f"😱 *Индекс Страха и Жадности*\n```\n[{bar}]\n```\n"
        f"{fg['emoji']} *{fg['value']}/100* — {fg['label']}",
        parse_mode=ParseMode.MARKDOWN)

# ══════════════════════════════════════════════════════════════
#  TEXT MESSAGE HANDLER (for custom amount input)
# ══════════════════════════════════════════════════════════════
async def text_handler(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    text=update.message.text.strip()
    waiting=USER_DATA[uid].get("waiting_custom_amount")
    if not waiting: return

    try:
        amount=float(text.replace("$","").replace(",","."))
        if amount<=0: raise ValueError
    except:
        await update.message.reply_text(
            "❌ Введите число, например: `25.5`",
            parse_mode=ParseMode.MARKDOWN)
        return

    USER_DATA[uid]["waiting_custom_amount"]=None
    action=waiting["action"]; coin=waiting["coin"]
    trade_type=waiting.get("trade_type","spot")

    if action in ("buy","sell"):
        side="BUY" if action=="buy" else "SELL"
        await _execute_trade(update, ctx, coin, side, amount,
                             confirmed=False, trade_type=trade_type)
    elif action=="auto_size":
        USER_DATA[uid]["auto_size"]=amount
        await update.message.reply_text(
            f"✅ Сумма авто-трейда: `${amount}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=auto_menu_kb(uid))
    elif action in ("confirm_buy","confirm_sell"):
        side="BUY" if "buy" in action else "SELL"
        await _execute_trade(update, ctx, coin, side, amount,
                             confirmed=False, trade_type=trade_type)

# ══════════════════════════════════════════════════════════════
#  CALLBACK HANDLER
# ══════════════════════════════════════════════════════════════
async def callback_handler(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    d=q.data; uid=update.effective_user.id
    USER_DATA[uid]["chat_id"]=update.effective_chat.id

    # ── MAIN MENU ────────────────────────────────────────────
    if d=="m_main":
        await q.edit_message_text(
            "🤖 *Binance Pro Bot*\n\n👇 Выберите действие:",
            parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())

    elif d=="m_buy":
        await q.edit_message_text("🛒 *КУПИТЬ — Выберите монету:*",
            parse_mode=ParseMode.MARKDOWN, reply_markup=coin_kb("buyc","m_main"))

    elif d=="m_sell":
        await q.edit_message_text("💰 *ПРОДАТЬ — Выберите монету:*",
            parse_mode=ParseMode.MARKDOWN, reply_markup=coin_kb("sellc","m_main"))

    elif d=="m_portfolio":
        await q.edit_message_text(
            portfolio_text(uid), parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

    elif d=="m_orders":
        orders=USER_DATA[uid]["orders"]
        if not orders: txt="📭 Нет сделок."
        else:
            lines=["📖 *Последние сделки*\n"]
            for o in orders[:8]:
                e="🟢" if o["side"]=="BUY" else "🔴"
                tl=TRADE_TYPES.get(o.get("type","spot"),"")
                lines.append(f"{e} *{o['symbol']}* {tl} `${o['total']:.2f}` — _{o['time']}_")
            txt="\n".join(lines)
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

    elif d=="m_balance":
        bal=get_account_balance()
        if not bal["ok"]: txt=f"❌ {bal['error']}"
        else:
            mt=" _(Демо)_" if bal.get("mock") else ""
            lines=[f"💳 *Баланс*{mt}\n"]
            for asset,qty in sorted(bal["balances"].items(),key=lambda x:-x[1])[:15]:
                lines.append(f"• *{asset}*: `{qty:.6f}`")
            txt="\n".join(lines)
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

    elif d=="m_prices":
        lines=["💹 *ТОП 15 ЦЕН*\n"]
        for c in TOP_COINS:
            t=get_price(c)
            if "error" not in t:
                e="🟢" if t["change"]>=0 else "🔴"
                lines.append(f"{e} *{c}*: `${t['price']:,.4f}` `{t['change']:+.2f}%`")
        await q.edit_message_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

    elif d=="m_screener":
        lines=["📋 *СКРИНЕР*\n"]; results=[]
        for c in TOP_COINS:
            t=get_price(c)
            if "error" not in t: results.append((c,t["change"],t["price"]))
        results.sort(key=lambda x:x[1],reverse=True)
        lines.append("🟢 *РОСТ*")
        for c,chg,pr in results[:5]:
            lines.append(f"  • *{c}*: `{chg:+.2f}%` @ `${pr:,.4f}`")
        lines.append("\n🔴 *ПАДЕНИЕ*")
        for c,chg,pr in results[-5:]:
            lines.append(f"  • *{c}*: `{chg:+.2f}%` @ `${pr:,.4f}`")
        await q.edit_message_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

    elif d=="m_fg":
        fg=fear_and_greed()
        bar="█"*int(fg["value"]/5)+"░"*(20-int(fg["value"]/5))
        await q.edit_message_text(
            f"😱 *Страх & Жадность*\n```\n[{bar}]\n```\n"
            f"{fg['emoji']} *{fg['value']}/100* — {fg['label']}",
            parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

    elif d=="m_whale":
        lines=["🐋 *Крупные сделки*\n"]
        for _ in range(5):
            c=random.choice(TOP_COINS); amt=round(random.uniform(50,3000),1)
            tp=get_price(c)["price"]; usd=int(amt*tp)
            side=random.choice(["🐋 ПОКУПКА","🦈 ПРОДАЖА"]); ago=random.randint(1,59)
            lines.append(f"{side} `{amt} {c}` ~`${usd:,}` — `{ago}мин назад`")
        await q.edit_message_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

    elif d=="m_help":
        await q.edit_message_text(
            "📌 Используйте `/help` для всех команд.",
            parse_mode=ParseMode.MARKDOWN, reply_markup=back_kb())

    # ── CHART ────────────────────────────────────────────────
    elif d=="m_chart":
        await q.edit_message_text(
            "📉 *График — Выберите монету:*",
            parse_mode=ParseMode.MARKDOWN, reply_markup=coin_kb("chartc","m_main"))

    elif d.startswith("chartc_"):
        coin=d.split("_")[1]
        await q.edit_message_text(
            f"📉 *{coin}USDT* — Выберите интервал:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=chart_interval_kb(coin))

    elif d.startswith("chart_"):
        parts=d.split("_"); coin=parts[1]; iv=parts[2]
        chart=ascii_chart(coin, iv)
        t=get_price(coin)
        await q.edit_message_text(
            f"📉 *{coin}USDT* [{iv}]\n```\n{chart}\n```",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=chart_interval_kb(coin))

    # ── ANALYSIS ─────────────────────────────────────────────
    elif d=="m_analysis":
        await q.edit_message_text(
            "🔬 *Анализ — Выберите монету:*",
            parse_mode=ParseMode.MARKDOWN, reply_markup=coin_kb("tac","m_main"))

    elif d.startswith("tac_"):
        coin=d.split("_")[1]; ta=compute_ta(coin); t=get_price(coin)
        await q.edit_message_text(
            _ta_text(coin.upper(), t.get("price",0), ta, "1h"),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 КУПИТЬ", callback_data=f"buyc_{coin}"),
                 InlineKeyboardButton("💰 ПРОДАТЬ",callback_data=f"sellc_{coin}"),
                 InlineKeyboardButton("🔙",         callback_data="m_analysis")]
            ]))

    # ── BUY COIN SELECTED ─────────────────────────────────────
    elif d.startswith("buyc_"):
        coin=d.split("_")[1]; t=get_price(coin)
        await q.edit_message_text(
            f"🛒 *КУПИТЬ {coin}USDT*\nЦена: `${t.get('price',0):,.4f}`\n\nВыберите сумму ($):",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=size_kb("preconfirm_buy", coin, "m_buy"))

    elif d.startswith("sellc_"):
        coin=d.split("_")[1]; t=get_price(coin)
        await q.edit_message_text(
            f"💰 *ПРОДАТЬ {coin}USDT*\nЦена: `${t.get('price',0):,.4f}`\n\nВыберите сумму ($):",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=size_kb("preconfirm_sell", coin, "m_sell"))

    elif d.startswith("preconfirm_buy_") or d.startswith("preconfirm_sell_"):
        parts=d.split("_"); side="BUY" if parts[1]=="buy" else "SELL"
        coin=parts[2]; amount=float(parts[3])
        uid_tt=USER_DATA[uid]["auto_type"]
        await _execute_trade(update, ctx, coin, side, amount,
                             confirmed=False, trade_type=uid_tt)

    # ── CUSTOM AMOUNT ─────────────────────────────────────────
    elif d.startswith("custom_amount_"):
        parts=d.split("_")
        # custom_amount_{action}_{coin}  OR  custom_amount_confirm_{side}_{coin}_{type}
        if parts[2]=="confirm":
            action=f"confirm_{parts[3]}"; coin=parts[4]
            trade_type=parts[5] if len(parts)>5 else "spot"
        else:
            action=parts[2]; coin=parts[3]
            trade_type=USER_DATA[uid]["auto_type"]
        USER_DATA[uid]["waiting_custom_amount"]={
            "action":action,"coin":coin,"trade_type":trade_type}
        await q.edit_message_text(
            f"✏️ *Введите свою сумму в $*\nПример: `25.5`\n\nМонета: *{coin}USDT*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data="m_main")]]))

    # ── AUTO TRADE MENU ───────────────────────────────────────
    elif d=="m_auto_menu":
        auto_st="🟢 ВКЛ" if USER_DATA[uid]["auto_enabled"] else "🔴 ВЫКЛ"
        atype=TRADE_TYPES.get(USER_DATA[uid]["auto_type"],"")
        asize=USER_DATA[uid]["auto_size"]
        ncoins=len(USER_DATA[uid]["auto_coins"])
        await q.edit_message_text(
            f"🤖 *Авто-Трейд*\n\n"
            f"Статус: *{auto_st}*\n"
            f"Тип: {atype}\n"
            f"Сумма: `${asize}`\n"
            f"Монет выбрано: `{ncoins}/15`\n\n"
            f"_Бот анализирует RSI+MACD+BB и торгует автоматически_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=auto_menu_kb(uid))

    elif d=="auto_toggle":
        USER_DATA[uid]["auto_enabled"]=not USER_DATA[uid]["auto_enabled"]
        st="🟢 ВКЛЮЧЁН" if USER_DATA[uid]["auto_enabled"] else "🔴 ВЫКЛЮЧЕН"
        atype=TRADE_TYPES.get(USER_DATA[uid]["auto_type"],"")
        asize=USER_DATA[uid]["auto_size"]
        ncoins=len(USER_DATA[uid]["auto_coins"])
        await q.edit_message_text(
            f"🤖 *Авто-Трейд*\n\n"
            f"Статус: *{st}*\n"
            f"Тип: {atype}\n"
            f"Сумма: `${asize}`\n"
            f"Монет выбрано: `{ncoins}/15`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=auto_menu_kb(uid))

    elif d=="auto_type_menu":
        await q.edit_message_text(
            "🔧 *Тип торговли:*",
            parse_mode=ParseMode.MARKDOWN, reply_markup=auto_type_kb())

    elif d.startswith("set_atype_"):
        atype=d.split("_")[2]
        USER_DATA[uid]["auto_type"]=atype
        await q.edit_message_text(
            f"✅ Тип: *{TRADE_TYPES.get(atype,atype)}*",
            parse_mode=ParseMode.MARKDOWN, reply_markup=auto_menu_kb(uid))

    elif d=="auto_size_menu":
        await q.edit_message_text(
            "💵 *Сумма авто-трейда:*",
            parse_mode=ParseMode.MARKDOWN, reply_markup=auto_size_kb(uid))

    elif d.startswith("set_asize_"):
        val=d.split("_")[2]
        if val=="custom":
            USER_DATA[uid]["waiting_custom_amount"]={
                "action":"auto_size","coin":"","trade_type":""}
            await q.edit_message_text(
                "✏️ *Введите свою сумму в $*\nПример: `35`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Отмена", callback_data="m_auto_menu")]]))
        else:
            USER_DATA[uid]["auto_size"]=float(val)
            await q.edit_message_text(
                f"✅ Сумма: `${val}`",
                parse_mode=ParseMode.MARKDOWN, reply_markup=auto_menu_kb(uid))

    elif d=="auto_coins_menu":
        await q.edit_message_text(
            "🪙 *Монеты для авто-трейда:*\n_(✅ = включена)_",
            parse_mode=ParseMode.MARKDOWN, reply_markup=auto_coins_kb(uid))

    elif d.startswith("toggle_acoin_"):
        coin=d.split("_")[2]
        coins=USER_DATA[uid]["auto_coins"]
        if coin in coins: coins.remove(coin)
        else: coins.append(coin)
        await q.edit_message_text(
            "🪙 *Монеты для авто-трейда:*\n_(✅ = включена)_",
            parse_mode=ParseMode.MARKDOWN, reply_markup=auto_coins_kb(uid))

    elif d=="acoin_all":
        USER_DATA[uid]["auto_coins"]=list(TOP_COINS)
        await q.edit_message_text(
            "✅ Все 15 монет выбраны",
            parse_mode=ParseMode.MARKDOWN, reply_markup=auto_coins_kb(uid))

    elif d=="acoin_none":
        USER_DATA[uid]["auto_coins"]=[]
        await q.edit_message_text(
            "❌ Все монеты сброшены",
            parse_mode=ParseMode.MARKDOWN, reply_markup=auto_coins_kb(uid))

    elif d=="auto_scan":
        await q.edit_message_text("🔍 Сканирование...")
        best=await _scan_best(uid)
        if best:
            coin,ta=best
            await q.edit_message_text(
                f"🏆 *{coin}USDT* — {ta['signal']}\nRSI: `{ta['rsi']}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 Торговать", callback_data=f"auto_do_{coin}"),
                     InlineKeyboardButton("❌ Пропустить",callback_data="m_auto_menu")]
                ]))
        else:
            await q.edit_message_text("⚪ Нет сильных сигналов.",
                                      reply_markup=back_kb("m_auto_menu"))

    elif d.startswith("auto_do_"):
        coin=d.split("_")[2]
        await do_auto_trade(uid, update.effective_chat.id, coin, ctx)

    # ── ALERTS MENU ───────────────────────────────────────────
    elif d=="m_alerts_menu":
        alerts=USER_DATA[uid]["alerts"]
        if not alerts: txt="🔕 *Алерты*\n\nНет активных алертов."
        else:
            lines=["🔔 *Активные алерты:*\n"]
            for i,a in enumerate(alerts,1):
                e="⬆️" if a["condition"]=="above" else "⬇️"
                lines.append(f"`{i}.` *{a['symbol']}* {e} `${a['price']:,.2f}`")
            txt="\n".join(lines)
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=alerts_menu_kb(uid))

    elif d=="alert_add":
        await q.edit_message_text(
            "🔔 *Добавить алерт — Выберите монету:*",
            parse_mode=ParseMode.MARKDOWN, reply_markup=alert_coin_kb())

    elif d.startswith("alert_coin_") and not d.startswith("alert_cond_"):
        coin=d.split("_")[2]
        t=get_price(coin)
        price=t.get("price",0)
        await q.edit_message_text(
            f"🔔 *Алерт — {coin}USDT*\n"
            f"Текущая цена: `${price:,.4f}`\n\n"
            f"Выберите условие:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=alert_condition_kb(coin))

    elif d.startswith("alert_cond_"):
        parts=d.split("_")
        coin=parts[2]; cond=parts[3]
        USER_DATA[uid]["waiting_alert_coin"]={"coin": coin, "cond": cond}
        cond_text="выше ⬆️" if cond=="above" else "ниже ⬇️"
        t=get_price(coin)
        price=t.get("price",0)
        await q.edit_message_text(
            f"🔔 *{coin}USDT — цена {cond_text}*\n"
            f"Текущая цена: `${price:,.4f}`\n\n"
            f"✏️ *Введите целевую цену:*\n"
            f"Например: `{int(price*1.05)}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data="m_alerts_menu")]]))

    elif d=="alert_clear":
        USER_DATA[uid]["alerts"]=[]
        await q.edit_message_text("🗑 Все алерты удалены.",
                                  reply_markup=back_kb("m_main"))

    # ── CONFIRM / CANCEL ──────────────────────────────────────
    elif d.startswith("confirm_"):
        parts=d.split("_")
        side=parts[1].upper(); coin=parts[2]
        amount=float(parts[3])
        trade_type=parts[4] if len(parts)>4 else USER_DATA[uid]["auto_type"]
        jobs=ctx.job_queue.get_jobs_by_name(f"autoconfirm_{uid}")
        for j in jobs: j.schedule_removal()
        USER_DATA[uid]["pending_trade"]=None
        await _execute_trade(update, ctx, coin, side, amount,
                             confirmed=True, trade_type=trade_type,
                             auto_note="Пользователь подтвердил")

    elif d=="cancel_trade":
        jobs=ctx.job_queue.get_jobs_by_name(f"autoconfirm_{uid}")
        for j in jobs: j.schedule_removal()
        USER_DATA[uid]["pending_trade"]=None
        await q.edit_message_text("❌ Сделка отменена.", reply_markup=back_kb())

    elif d=="noop":
        pass

# ══════════════════════════════════════════════════════════════
#  TEXT HANDLER for alert condition input
# ══════════════════════════════════════════════════════════════
async def full_text_handler(update:Update, ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    text=update.message.text.strip()

    # Alert condition input
    waiting_alert=USER_DATA[uid].get("waiting_alert_coin")
    if waiting_alert:
        # Now waiting_alert is a dict: {"coin": ..., "cond": ...}
        if isinstance(waiting_alert, dict):
            coin_a=waiting_alert["coin"]
            cond=waiting_alert["cond"]
        else:
            # legacy fallback
            coin_a=waiting_alert; cond="above"
        try:
            price_a=float(text.replace("$","").replace(",",".").replace(" ",""))
            if price_a<=0: raise ValueError
            USER_DATA[uid]["alerts"].append(
                {"symbol":sym(coin_a),"condition":cond,
                 "price":price_a,"chat_id":update.effective_chat.id})
            USER_DATA[uid]["waiting_alert_coin"]=None
            e="⬆️" if cond=="above" else "⬇️"
            await update.message.reply_text(
                f"✅ *Алерт установлен!*\n\n"
                f"Монета: *{sym(coin_a)}*\n"
                f"Условие: {e} `${price_a:,.2f}`\n\n"
                f"_Уведомление придёт когда цена достигнет цели_",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=alerts_menu_kb(uid))
            return
        except:
            t_now=get_price(coin_a)
            await update.message.reply_text(
                f"❌ Введите только число!\nПример: `{int(t_now.get('price',1000)*1.05)}`",
                parse_mode=ParseMode.MARKDOWN)
            return

    # Custom amount input
    waiting_amount=USER_DATA[uid].get("waiting_custom_amount")
    if waiting_amount:
        try:
            amount=float(text.replace("$","").replace(",","."))
            if amount<=0: raise ValueError
        except:
            await update.message.reply_text(
                "❌ Введите число: `25.5`", parse_mode=ParseMode.MARKDOWN)
            return
        USER_DATA[uid]["waiting_custom_amount"]=None
        action=waiting_amount["action"]; coin=waiting_amount["coin"]
        trade_type=waiting_amount.get("trade_type",USER_DATA[uid]["auto_type"])

        if action=="auto_size":
            USER_DATA[uid]["auto_size"]=amount
            await update.message.reply_text(
                f"✅ Сумма авто: `${amount}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=auto_menu_kb(uid))
        elif action in ("buy","preconfirm_buy"):
            await _execute_trade(update, ctx, coin, "BUY", amount,
                                 confirmed=False, trade_type=trade_type)
        elif action in ("sell","preconfirm_sell"):
            await _execute_trade(update, ctx, coin, "SELL", amount,
                                 confirmed=False, trade_type=trade_type)
        elif "buy" in action:
            await _execute_trade(update, ctx, coin, "BUY", amount,
                                 confirmed=False, trade_type=trade_type)
        elif "sell" in action:
            await _execute_trade(update, ctx, coin, "SELL", amount,
                                 confirmed=False, trade_type=trade_type)

# ══════════════════════════════════════════════════════════════
#  BACKGROUND JOBS
# ══════════════════════════════════════════════════════════════
async def check_alerts_job(ctx:ContextTypes.DEFAULT_TYPE):
    for uid,data in list(USER_DATA.items()):
        triggered,remaining=[],[]
        for alert in data.get("alerts",[]):
            t=get_price(alert["symbol"])
            if "error" in t: remaining.append(alert); continue
            p=t["price"]
            hit=(alert["condition"]=="above" and p>=alert["price"]) or \
                (alert["condition"]=="below"  and p<=alert["price"])
            if hit: triggered.append((alert,p))
            else:   remaining.append(alert)
        data["alerts"]=remaining
        for alert,cur in triggered:
            e="⬆️" if alert["condition"]=="above" else "⬇️"
            try:
                await ctx.bot.send_message(
                    alert["chat_id"],
                    f"🔔 *АЛЕРТ!* *{alert['symbol']}* {e} `${alert['price']:,.2f}`\n"
                    f"Текущая: `${cur:,.4f}`",
                    parse_mode=ParseMode.MARKDOWN)
            except Exception as err:
                log.error(f"Alert error: {err}")

async def auto_trade_job(ctx:ContextTypes.DEFAULT_TYPE):
    """Runs every 5 minutes, checks signals for users with auto_enabled=True"""
    for uid,data in list(USER_DATA.items()):
        if not data.get("auto_enabled"): continue
        if not data.get("chat_id"):      continue
        if data.get("pending_trade"):    continue  # already waiting
        coins=data["auto_coins"] or TOP_COINS
        coin=random.choice(coins)  # pick random coin to check
        ta=compute_ta(coin)
        if abs(ta["score"])>=2:
            await do_auto_trade(uid, data["chat_id"], coin, ctx)
            await asyncio.sleep(2)  # small delay between users

# ══════════════════════════════════════════════════════════════
#  HEALTH SERVER
# ══════════════════════════════════════════════════════════════
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"Binance Bot OK")
    def log_message(self,*args): pass

def run_health_server():
    server=HTTPServer(("0.0.0.0",PORT),HealthHandler)
    log.info(f"Health server on port {PORT}")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════
async def main():
    if TELEGRAM_TOKEN=="YOUR_TOKEN":
        print("Set TELEGRAM_TOKEN in Render Environment Variables!"); return

    Thread(target=run_health_server, daemon=True).start()

    app=Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("buy",       cmd_buy))
    app.add_handler(CommandHandler("sell",      cmd_sell))
    app.add_handler(CommandHandler("auto",      cmd_auto))
    app.add_handler(CommandHandler("scan",      cmd_scan))
    app.add_handler(CommandHandler("price",     cmd_price))
    app.add_handler(CommandHandler("chart",     cmd_chart))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("orders",    cmd_orders))
    app.add_handler(CommandHandler("balance",   cmd_balance))
    app.add_handler(CommandHandler("analysis",  cmd_analysis))
    app.add_handler(CommandHandler("alert",     cmd_alert))
    app.add_handler(CommandHandler("fg",        cmd_fg))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, full_text_handler))

    app.job_queue.run_repeating(check_alerts_job,  interval=60,  first=15)
    app.job_queue.run_repeating(auto_trade_job,    interval=300, first=60)

    log.info("🚀 Bot v3.0 started!")

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__=="__main__":
    asyncio.run(main())
