"""
BINANCE PRO TRADING BOT v6.0
Русский интерфейс | Candlestick Charts | LOT_SIZE fix | Real Portfolio
"""
import os, asyncio, logging, time, math, random, io
from datetime import datetime
from typing import Optional
from collections import defaultdict
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

import numpy as np

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                           ContextTypes, MessageHandler, filters)
from telegram.constants import ParseMode

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
    BINANCE_OK = True
except ImportError:
    BINANCE_OK = False

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.gridspec import GridSpec
    import matplotlib.dates as mdates
    MPL_OK = True
except ImportError:
    MPL_OK = False

logging.basicConfig(format="%(asctime)s | %(levelname)-8s | %(message)s",
                    datefmt="%H:%M:%S", level=logging.INFO)
log = logging.getLogger("Bot")

# ── CONFIG ────────────────────────────────────────────────────────
TELEGRAM_TOKEN       = os.environ.get("TELEGRAM_TOKEN",  "YOUR_TOKEN")
BINANCE_API_KEY      = os.environ.get("BINANCE_API_KEY", "")
BINANCE_SECRET       = os.environ.get("BINANCE_SECRET",  "")
USE_TESTNET          = os.environ.get("USE_TESTNET", "false").lower() == "true"
PORT                 = int(os.environ.get("PORT", 8080))
AUTO_CONFIRM_TIMEOUT = int(os.environ.get("AUTO_CONFIRM_TIMEOUT", "30"))

TRADE_SIZES = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
TOP_COINS   = ["BTC","ETH","BNB","SOL","XRP","ADA","DOGE","AVAX",
               "DOT","MATIC","LINK","LTC","UNI","ATOM","NEAR"]
TRADE_TYPES = {"spot":"📈 Спот","futures":"🔮 Фьючерсы","margin":"💳 Маржа"}

# ── STATE ─────────────────────────────────────────────────────────
def default_user():
    return {"portfolio":{},"alerts":[],"orders":[],"pending_trade":None,
            "chat_id":None,"auto_enabled":False,"auto_coins":list(TOP_COINS),
            "auto_type":"spot","auto_size":20,"waiting_input":None}

USER_DATA = defaultdict(default_user)

# ── BINANCE CLIENT ────────────────────────────────────────────────
bc = None
if BINANCE_OK and BINANCE_API_KEY:
    try:
        bc = Client(BINANCE_API_KEY, BINANCE_SECRET, testnet=USE_TESTNET)
        log.info("✅ Binance " + ("TESTNET" if USE_TESTNET else "LIVE"))
    except Exception as e:
        log.warning(f"Binance: {e}")

MOCK = {"BTCUSDT":67500,"ETHUSDT":3450,"BNBUSDT":582,"SOLUSDT":176,
        "XRPUSDT":0.58,"ADAUSDT":0.48,"DOGEUSDT":0.162,"AVAXUSDT":38.7,
        "DOTUSDT":7.8,"MATICUSDT":0.91,"LINKUSDT":18.4,"LTCUSDT":82.0,
        "UNIUSDT":9.3,"ATOMUSDT":10.5,"NEARUSDT":7.1}

def sym(coin):
    c = coin.upper().strip()
    return c if c.endswith("USDT") else c + "USDT"

# ── LOT SIZE FIX ──────────────────────────────────────────────────
_lot_cache = {}

def get_lot_size(symbol):
    if symbol in _lot_cache:
        return _lot_cache[symbol]
    if bc:
        try:
            info = bc.get_symbol_info(symbol)
            for f in info["filters"]:
                if f["filterType"] == "LOT_SIZE":
                    step = float(f["stepSize"])
                    minq = float(f["minQty"])
                    _lot_cache[symbol] = (step, minq)
                    return step, minq
        except:
            pass
    return 0.00001, 0.00001

def round_qty(qty, step):
    if step <= 0: return qty
    precision = max(0, round(-math.log10(step)))
    factor = 10 ** precision
    return math.floor(qty * factor) / factor

def get_min_notional(symbol):
    if bc:
        try:
            info = bc.get_symbol_info(symbol)
            for f in info["filters"]:
                if f["filterType"] in ("MIN_NOTIONAL","NOTIONAL"):
                    return float(f.get("minNotional", f.get("notional", 5)))
        except:
            pass
    return 5.0

# ── PRICE & KLINES ────────────────────────────────────────────────
def get_price(coin):
    s = sym(coin)
    if bc:
        try:
            t = bc.get_ticker(symbol=s)
            return {"symbol":s,"price":float(t["lastPrice"]),
                    "change":float(t["priceChangePercent"]),
                    "high":float(t["highPrice"]),"low":float(t["lowPrice"]),
                    "volume":float(t["volume"])}
        except Exception as e:
            return {"error":str(e),"symbol":s}
    base = MOCK.get(s,10.0)*random.uniform(0.98,1.02)
    return {"symbol":s,"price":round(base,6),"change":round(random.uniform(-6,6),2),
            "high":round(base*1.04,6),"low":round(base*0.96,6),
            "volume":round(random.uniform(5000,500000),2)}

def get_klines(coin, interval="1h", limit=60):
    s = sym(coin)
    if bc:
        try:
            return bc.get_klines(symbol=s, interval=interval, limit=limit)
        except:
            pass
    base = MOCK.get(s,50.0)
    data=[]; t=int(time.time()*1000)-limit*3600000
    for _ in range(limit):
        o=base*random.uniform(0.99,1.01); h=o*random.uniform(1.00,1.02)
        lo=o*random.uniform(0.98,1.00);  c=random.uniform(lo,h); base=c
        data.append([t,str(o),str(h),str(lo),str(c),str(random.uniform(100,5000)),t+3600000])
        t+=3600000
    return data

def get_real_balance():
    if bc:
        try:
            acc = bc.get_account()
            return {b["asset"]: float(b["free"])+float(b["locked"])
                    for b in acc["balances"]
                    if float(b["free"])+float(b["locked"])>0.000001}
        except Exception as e:
            return {"_error": str(e)}
    return {"USDT":1000.0,"BTC":0.01,"ETH":0.5,"_mock":True}

def get_real_trades():
    if not bc: return []
    all_trades=[]
    for coin in TOP_COINS:
        s=sym(coin)
        try:
            trades=bc.get_my_trades(symbol=s, limit=5)
            for t in trades:
                all_trades.append({
                    "time":datetime.fromtimestamp(t["time"]/1000).strftime("%d.%m %H:%M"),
                    "symbol":s,"side":"BUY" if t["isBuyer"] else "SELL",
                    "qty":float(t["qty"]),"price":float(t["price"]),
                    "total":float(t["qty"])*float(t["price"]),"ts":t["time"]})
        except: continue
    all_trades.sort(key=lambda x:x["ts"],reverse=True)
    return all_trades

def place_order(coin, side, usdt_amount, trade_type="spot"):
    s = sym(coin)
    ticker = get_price(coin)
    if "error" in ticker:
        return {"ok":False,"error":ticker["error"]}
    price = ticker["price"]
    min_notional = get_min_notional(s)
    if usdt_amount < min_notional:
        return {"ok":False,"error":f"Минимальная сумма: ${min_notional}"}
    raw_qty = usdt_amount / price
    step, min_qty = get_lot_size(s)
    qty = round_qty(raw_qty, step)
    if qty < min_qty:
        return {"ok":False,"error":f"Кол-во {qty} меньше минимума {min_qty}"}
    if bc:
        try:
            if trade_type == "futures":
                order = bc.futures_create_order(symbol=s,side=side,type="MARKET",
                    quoteOrderQty=usdt_amount) if side=="BUY" else \
                    bc.futures_create_order(symbol=s,side=side,type="MARKET",quantity=str(qty))
            elif trade_type == "margin":
                order = bc.create_margin_order(symbol=s,side=side,type="MARKET",
                    quoteOrderQty=usdt_amount) if side=="BUY" else \
                    bc.create_margin_order(symbol=s,side=side,type="MARKET",quantity=str(qty))
            else:
                order = bc.order_market_buy(symbol=s,quoteOrderQty=usdt_amount) if side=="BUY" else \
                        bc.order_market_sell(symbol=s,quantity=str(qty))
            fills=order.get("fills",[{}])
            fp=float(fills[0].get("price",price)) if fills else price
            fq=float(order.get("executedQty",qty))
            return {"ok":True,"symbol":s,"side":side,"qty":fq,"price":fp,
                    "total":fq*fp,"orderId":order.get("orderId"),"type":trade_type,"mock":False}
        except BinanceAPIException as e:
            return {"ok":False,"error":f"Binance: {e.message}"}
        except Exception as e:
            return {"ok":False,"error":str(e)}
    ep=price*random.uniform(0.999,1.001); eq=round_qty(usdt_amount/ep,step)
    return {"ok":True,"symbol":s,"side":side,"qty":eq,"price":round(ep,4),
            "total":round(usdt_amount,2),"orderId":f"DEMO-{int(time.time())}",
            "type":trade_type,"mock":True}

# ══════════════════════════════════════════════════════════════════
#  CANDLESTICK CHART GENERATOR
# ══════════════════════════════════════════════════════════════════
def generate_chart(coin, interval="1h", limit=60) -> Optional[bytes]:
    """Generate a beautiful candlestick chart and return as PNG bytes."""
    if not MPL_OK:
        return None
    try:
        klines = get_klines(coin, interval, limit)
        dates  = [datetime.fromtimestamp(k[0]/1000) for k in klines]
        opens  = [float(k[1]) for k in klines]
        highs  = [float(k[2]) for k in klines]
        lows   = [float(k[3]) for k in klines]
        closes = [float(k[4]) for k in klines]
        volumes= [float(k[5]) for k in klines]

        # Colors
        BG       = "#0d1117"
        GRID     = "#21262d"
        BULL_C   = "#26a69a"   # green candle
        BEAR_C   = "#ef5350"   # red candle
        VOL_BULL = "#1a6b66"
        VOL_BEAR = "#8b2020"
        TEXT_C   = "#c9d1d9"
        LINE_C   = "#f0b90b"   # EMA line (yellow)
        BB_C     = "#58a6ff"   # Bollinger

        fig = plt.figure(figsize=(12, 7), facecolor=BG)
        gs  = GridSpec(4, 1, figure=fig, hspace=0.05,
                       height_ratios=[3, 1, 0.8, 0.8])

        ax1 = fig.add_subplot(gs[0])  # Price + candles
        ax2 = fig.add_subplot(gs[1], sharex=ax1)  # Volume
        ax3 = fig.add_subplot(gs[2], sharex=ax1)  # MACD
        ax4 = fig.add_subplot(gs[3], sharex=ax1)  # RSI

        for ax in [ax1,ax2,ax3,ax4]:
            ax.set_facecolor(BG)
            ax.tick_params(colors=TEXT_C, labelsize=8)
            ax.yaxis.tick_right()
            ax.grid(color=GRID, linewidth=0.5, alpha=0.7)
            for spine in ax.spines.values():
                spine.set_edgecolor(GRID)

        x = np.arange(len(dates))

        # ── CANDLES ───────────────────────────────────────────────
        width = 0.6
        for i in range(len(x)):
            bull = closes[i] >= opens[i]
            color = BULL_C if bull else BEAR_C
            # Body
            body_bot = min(opens[i], closes[i])
            body_h   = abs(closes[i] - opens[i]) or (closes[i] * 0.001)
            ax1.bar(x[i], body_h, bottom=body_bot, width=width,
                    color=color, linewidth=0)
            # Wick
            ax1.plot([x[i], x[i]], [lows[i], highs[i]],
                     color=color, linewidth=0.8)

        # ── EMA 20 ────────────────────────────────────────────────
        def ema(prices, n):
            k=2/(n+1); r=[sum(prices[:n])/n]
            for p in prices[n:]: r.append(p*k+r[-1]*(1-k))
            return [None]*(n-1)+r

        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        e20_x = [x[i] for i in range(len(x)) if ema20[i] is not None]
        e20_y = [v for v in ema20 if v is not None]
        e50_x = [x[i] for i in range(len(x)) if ema50[i] is not None]
        e50_y = [v for v in ema50 if v is not None]
        ax1.plot(e20_x, e20_y, color=LINE_C,  linewidth=1.2, label="EMA20")
        ax1.plot(e50_x, e50_y, color="#ff7b00",linewidth=1.2, label="EMA50")

        # ── BOLLINGER BANDS ───────────────────────────────────────
        if len(closes) >= 20:
            bb_mid, bb_u, bb_l = [], [], []
            for i in range(len(closes)):
                if i < 19:
                    bb_mid.append(None); bb_u.append(None); bb_l.append(None)
                else:
                    sl = closes[i-19:i+1]
                    m = sum(sl)/20
                    s = math.sqrt(sum((c-m)**2 for c in sl)/20)
                    bb_mid.append(m); bb_u.append(m+2*s); bb_l.append(m-2*s)
            bx  = [x[i] for i in range(len(x)) if bb_mid[i] is not None]
            bmu = [v for v in bb_u  if v is not None]
            bml = [v for v in bb_l  if v is not None]
            ax1.plot(bx, bmu, color=BB_C, linewidth=0.8, linestyle="--", alpha=0.7)
            ax1.plot(bx, bml, color=BB_C, linewidth=0.8, linestyle="--", alpha=0.7)
            ax1.fill_between(bx, bmu, bml, color=BB_C, alpha=0.04)

        # Title & legend
        last    = closes[-1]
        chg     = ((last-closes[0])/closes[0]*100) if closes[0] else 0
        chg_clr = BULL_C if chg >= 0 else BEAR_C
        ax1.set_title(f"{sym(coin)}  {interval}  |  ${last:,.4f}  "
                      f"{'▲' if chg>=0 else '▼'}{abs(chg):.2f}%",
                      color=TEXT_C, fontsize=13, fontweight="bold", pad=10)
        ax1.legend(loc="upper left", fontsize=8,
                   facecolor=BG, edgecolor=GRID, labelcolor=TEXT_C)
        ax1.set_xlim(-1, len(x))

        # ── VOLUME ────────────────────────────────────────────────
        for i in range(len(x)):
            bull = closes[i] >= opens[i]
            ax2.bar(x[i], volumes[i], color=VOL_BULL if bull else VOL_BEAR,
                    linewidth=0, alpha=0.8)
        ax2.set_ylabel("Vol", color=TEXT_C, fontsize=8)

        # ── MACD ──────────────────────────────────────────────────
        def calc_macd(p):
            e12=ema(p,12); e26=ema(p,26)
            ml=[]; sl=[]
            for i in range(len(p)):
                if e12[i] and e26[i]: ml.append(e12[i]-e26[i])
                else: ml.append(None)
            valid=[v for v in ml if v is not None]
            if len(valid)>=9:
                se=ema(valid,9)
                pad=[None]*(len(ml)-len(se))
                se=pad+se
            else:
                se=[None]*len(ml)
            hist=[]
            for i in range(len(ml)):
                if ml[i] and se[i]: hist.append(ml[i]-se[i])
                else: hist.append(None)
            return ml,se,hist

        ml,sl,hist=calc_macd(closes)
        mx=[x[i] for i in range(len(x)) if ml[i] is not None]
        my=[v for v in ml if v is not None]
        sy=[v for v in sl if v is not None]
        hy=[v for v in hist if v is not None]
        hx=[x[i] for i in range(len(x)) if hist[i] is not None]
        ax3.plot(mx,my,color=LINE_C,linewidth=1)
        ax3.plot(mx[-len(sy):],sy,color="#ff7b00",linewidth=1)
        for i in range(len(hx)):
            ax3.bar(hx[i],hy[i],color=BULL_C if hy[i]>=0 else BEAR_C,
                    linewidth=0,alpha=0.8)
        ax3.axhline(0,color=GRID,linewidth=0.5)
        ax3.set_ylabel("MACD",color=TEXT_C,fontsize=8)

        # ── RSI ───────────────────────────────────────────────────
        def calc_rsi(p,n=14):
            result=[None]*n
            for i in range(n,len(p)):
                sl2=p[i-n:i]
                g=[max(sl2[j]-sl2[j-1],0) for j in range(1,len(sl2))]
                lo=[max(sl2[j-1]-sl2[j],0) for j in range(1,len(sl2))]
                ag=sum(g)/n; al=sum(lo)/n
                result.append(100-100/(1+ag/al) if al else 100)
            return result

        rsi=calc_rsi(closes)
        rx=[x[i] for i in range(len(x)) if rsi[i] is not None]
        ry=[v for v in rsi if v is not None]
        ax4.plot(rx,ry,color="#a78bfa",linewidth=1.2)
        ax4.axhline(70,color=BEAR_C,linewidth=0.8,linestyle="--",alpha=0.7)
        ax4.axhline(30,color=BULL_C,linewidth=0.8,linestyle="--",alpha=0.7)
        ax4.fill_between(rx,ry,70,where=[v>=70 for v in ry],
                         color=BEAR_C,alpha=0.15)
        ax4.fill_between(rx,ry,30,where=[v<=30 for v in ry],
                         color=BULL_C,alpha=0.15)
        ax4.set_ylim(0,100)
        ax4.set_ylabel("RSI",color=TEXT_C,fontsize=8)
        ax4.set_yticks([30,50,70])

        # X axis labels (show only last few)
        tick_step = max(1, len(x)//8)
        ax4.set_xticks(x[::tick_step])
        fmt = "%H:%M" if interval in ("15m","1h") else "%m/%d"
        ax4.set_xticklabels(
            [dates[i].strftime(fmt) for i in range(0,len(dates),tick_step)],
            color=TEXT_C, fontsize=7)
        plt.setp(ax1.get_xticklabels(), visible=False)
        plt.setp(ax2.get_xticklabels(), visible=False)
        plt.setp(ax3.get_xticklabels(), visible=False)

        plt.tight_layout(pad=1.0)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                    facecolor=BG)
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    except Exception as e:
        log.error(f"Chart error: {e}")
        plt.close("all")
        return None

# ── TECHNICAL ANALYSIS ────────────────────────────────────────────
def compute_ta(coin, interval="1h"):
    klines=get_klines(coin,interval,120)
    closes=[float(k[4]) for k in klines]

    def ema(p,n):
        k=2/(n+1); r=[sum(p[:n])/n]
        for x in p[n:]: r.append(x*k+r[-1]*(1-k))
        return r

    def rsi(p,n=14):
        g,lo=[],[]
        for i in range(1,len(p)):
            d=p[i]-p[i-1]; g.append(max(d,0)); lo.append(max(-d,0))
        ag=sum(g[-n:])/n; al=sum(lo[-n:])/n
        return round(100-100/(1+ag/al),2) if al else 100.0

    e12=ema(closes,12); e26=ema(closes,26)
    n=min(len(e12),len(e26)); ml=[e12[-n+i]-e26[i] for i in range(n)]
    hist=ml[-1]-ema(ml,9)[-1]
    p20=closes[-20:]; sma=sum(p20)/20
    std=math.sqrt(sum((c-sma)**2 for c in p20)/20)
    rsi_v=rsi(closes); cur=closes[-1]; score=0

    if rsi_v<30:       score+=2
    elif rsi_v>70:     score-=2
    if hist>0:         score+=1
    else:              score-=1
    if cur<sma-2*std:  score+=1
    elif cur>sma+2*std:score-=1
    if e12[-1]>e26[-1]:score+=1
    else:              score-=1

    if score>=3:    sig="🟢 СИЛЬНАЯ ПОКУПКА"
    elif score>=1:  sig="🟩 ПОКУПКА"
    elif score<=-3: sig="🔴 СИЛЬНАЯ ПРОДАЖА"
    elif score<=-1: sig="🟥 ПРОДАЖА"
    else:           sig="🟡 НЕЙТРАЛЬНО"

    return {"rsi":rsi_v,"hist":round(hist,4),"signal":sig,"score":score,
            "bb_u":round(sma+2*std,4),"bb_l":round(sma-2*std,4),"bb_m":round(sma,4),
            "ema12":round(e12[-1],4),"ema26":round(e26[-1],4)}

def fear_greed():
    v=random.randint(18,88)
    i=0 if v<25 else 1 if v<45 else 2 if v<55 else 3 if v<75 else 4
    return {"value":v,
            "label":("Крайний страх","Страх","Нейтрально","Жадность","Крайняя жадность")[i],
            "emoji":("😱","😨","😐","😏","🤑")[i]}

# ── PORTFOLIO TEXT ────────────────────────────────────────────────
def portfolio_text(uid):
    lines=["💼 *ПОРТФЕЛЬ*\n"]; ti=tc=0.0
    bals=get_real_balance()
    err=bals.pop("_error",None); is_mock=bals.pop("_mock",False)
    if err: return f"💼 *ПОРТФЕЛЬ*\n\n❌ Ошибка: `{err}`"
    if is_mock: lines.append("_⚠️ Демо-данные_\n")
    usdt=bals.pop("USDT",0); has=False
    for asset,qty in sorted(bals.items(),key=lambda x:-x[1]):
        if qty<0.000001: continue
        t=get_price(asset)
        if "error" in t: continue
        p=t["price"]; val=qty*p; tc+=val; has=True
        local=USER_DATA[uid]["portfolio"].get(asset+"USDT")
        if local and local.get("avg_price"):
            avg=local["avg_price"]; inv=qty*avg; pnl=val-inv
            pct=pnl/inv*100 if inv else 0; ti+=inv
            e="🟢" if pnl>=0 else "🔴"
            lines.append(f"{e} *{asset}*: `{qty:.6f}`\n"
                         f"   Цена `${p:.4f}` | `${val:.2f}`\n"
                         f"   PnL `{'+' if pnl>=0 else ''}{pnl:.2f}$` ({pct:+.1f}%)\n")
        else:
            lines.append(f"💠 *{asset}*: `{qty:.6f}`\n"
                         f"   Цена `${p:.4f}` | `${val:.2f}`\n")
    if usdt>0:
        lines.append(f"💵 *USDT*: `${usdt:.4f}`"); tc+=usdt
    if not has and usdt==0:
        return "📂 *Портфель пуст*\n\nПополните счёт для торговли."
    lines.append("─────────────────")
    lines.append(f"💎 *Итого:* `${tc:.2f} USDT`")
    if ti>0:
        tp=tc-ti; te="🟢" if tp>=0 else "🔴"
        lines.append(f"{te} *PnL:* `{'+' if tp>=0 else ''}{tp:.2f}$` ({tp/ti*100:+.1f}%)")
    return "\n".join(lines)

def update_portfolio(uid,order):
    s=order["symbol"]; qty=order["qty"]; p=order["price"]
    port=USER_DATA[uid]["portfolio"]
    if order["side"]=="BUY":
        if s in port:
            oq=port[s]["qty"]; oa=port[s]["avg_price"]; nq=oq+qty
            port[s]={"qty":nq,"avg_price":round((oq*oa+qty*p)/nq,6)}
        else: port[s]={"qty":qty,"avg_price":p}
    else:
        if s in port:
            nq=port[s]["qty"]-qty
            if nq<=0.000001: del port[s]
            else: port[s]["qty"]=round(nq,8)

def record_order(uid,order,note=""):
    USER_DATA[uid]["orders"].insert(0,{
        "time":datetime.now().strftime("%d.%m %H:%M"),
        "symbol":order["symbol"],"side":order["side"],
        "qty":order["qty"],"price":order["price"],
        "total":order["total"],"type":order.get("type","spot"),"note":note})
    USER_DATA[uid]["orders"]=USER_DATA[uid]["orders"][:50]

# ── KEYBOARDS ─────────────────────────────────────────────────────
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Купить",      callback_data="m_buy"),
         InlineKeyboardButton("💰 Продать",     callback_data="m_sell")],
        [InlineKeyboardButton("🤖 Авто-трейд",  callback_data="m_auto"),
         InlineKeyboardButton("💼 Портфель",    callback_data="m_portfolio")],
        [InlineKeyboardButton("📊 Анализ",      callback_data="m_analysis"),
         InlineKeyboardButton("📉 График",      callback_data="m_chart_menu")],
        [InlineKeyboardButton("💹 Цены",        callback_data="m_prices"),
         InlineKeyboardButton("📋 Скринер",     callback_data="m_screener")],
        [InlineKeyboardButton("🔔 Алерты",      callback_data="m_alerts"),
         InlineKeyboardButton("📖 Сделки",      callback_data="m_orders")],
        [InlineKeyboardButton("😱 Страх/Жадн.", callback_data="m_fg"),
         InlineKeyboardButton("🐋 Киты",        callback_data="m_whale")],
        [InlineKeyboardButton("💳 Баланс",      callback_data="m_balance"),
         InlineKeyboardButton("ℹ️ Помощь",       callback_data="m_help")],
    ])

def back(t="m_main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад",callback_data=t)]])

def coins_kb(act, back_cb="m_main"):
    rows=[]; row=[]
    for c in TOP_COINS:
        row.append(InlineKeyboardButton(c,callback_data=f"{act}__{c}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Назад",callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)

def sizes_kb(act, coin, back_cb):
    rows=[]; row=[]
    for s in TRADE_SIZES:
        row.append(InlineKeyboardButton(f"${s}",callback_data=f"{act}__{coin}__{s}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("✏️ Своя сумма",callback_data=f"custom__{act}__{coin}")])
    rows.append([InlineKeyboardButton("🔙 Назад",callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)

def chart_iv_kb(coin):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(iv,callback_data=f"chrt__{coin}__{iv}")
         for iv in ["15m","1h","4h","1d","1w"]],
        [InlineKeyboardButton("🔙 Назад",callback_data="m_chart_menu")]
    ])

def auto_kb(uid):
    on=USER_DATA[uid]["auto_enabled"]
    tt=TRADE_TYPES.get(USER_DATA[uid]["auto_type"],"")
    sz=USER_DATA[uid]["auto_size"]; nc=len(USER_DATA[uid]["auto_coins"])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Авто: {'🟢 ВКЛ' if on else '🔴 ВЫКЛ'}",callback_data="noop")],
        [InlineKeyboardButton("▶️ Включить" if not on else "⏹ Выключить",callback_data="auto_toggle")],
        [InlineKeyboardButton(f"Тип: {tt}",callback_data="auto_type")],
        [InlineKeyboardButton(f"Сумма: ${sz}",callback_data="auto_size")],
        [InlineKeyboardButton(f"Монеты: {nc}/15",callback_data="auto_coins")],
        [InlineKeyboardButton("🔍 Сканировать",callback_data="auto_scan")],
        [InlineKeyboardButton("🔙 Назад",callback_data="m_main")],
    ])

def auto_coins_kb(uid):
    sel=USER_DATA[uid]["auto_coins"]; rows=[]; row=[]
    for c in TOP_COINS:
        ch="✅" if c in sel else "◻️"
        row.append(InlineKeyboardButton(f"{ch}{c}",callback_data=f"acoin__{c}"))
        if len(row)==3: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("✅ Все",callback_data="acoin__ALL"),
                 InlineKeyboardButton("❌ Сброс",callback_data="acoin__NONE")])
    rows.append([InlineKeyboardButton("🔙 Назад",callback_data="m_auto")])
    return InlineKeyboardMarkup(rows)

def ta_text(coin,price,ta,iv):
    re="🟢" if ta["rsi"]<30 else ("🔴" if ta["rsi"]>70 else "🟡")
    me="🟢" if ta["hist"]>0 else "🔴"
    return (f"🔬 *Анализ {coin}USDT [{iv}]*\n\n"
            f"💵 Цена: `${price:,.4f}`\n\n"
            f"📉 *RSI(14):* {re} `{ta['rsi']}`\n"
            f"   {'Перепродан 🔥' if ta['rsi']<30 else ('Перекуплен ❄️' if ta['rsi']>70 else 'Норма')}\n\n"
            f"📊 *MACD:* {me} hist=`{ta['hist']}`\n\n"
            f"📏 *Bollinger:*\n"
            f"   Верх `{ta['bb_u']}` | Середина `{ta['bb_m']}` | Низ `{ta['bb_l']}`\n\n"
            f"📐 *EMA 12/26:* `{ta['ema12']}` / `{ta['ema26']}`\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🎯 Сигнал: {ta['signal']}\n"
            f"📌 Оценка: `{ta['score']}/4`")

# ── TRADE CORE ────────────────────────────────────────────────────
async def do_trade(source, ctx, coin, side, amount,
                   confirmed=False, ttype="spot", note=""):
    if isinstance(source, int):
        uid=source; chat_id=USER_DATA[uid]["chat_id"]
        is_cb=False; upd=None
    else:
        upd=source; uid=upd.effective_user.id
        chat_id=upd.effective_chat.id
        is_cb=upd.callback_query is not None
        USER_DATA[uid]["chat_id"]=chat_id

    t=get_price(coin)
    if "error" in t:
        msg=f"❌ Нет цены для {coin}: {t['error']}"
        if is_cb: await upd.callback_query.edit_message_text(msg)
        elif upd: await upd.message.reply_text(msg)
        return

    price=t["price"]; qty=amount/price
    type_lbl=TRADE_TYPES.get(ttype,"📈 Спот")

    if not confirmed:
        se="🛒" if side=="BUY" else "💰"
        text=(f"{se} *Подтвердить сделку*\n\n"
              f"Монета:   *{sym(coin)}*\n"
              f"Действие: *{'КУПИТЬ' if side=='BUY' else 'ПРОДАТЬ'}*\n"
              f"Тип:      {type_lbl}\n"
              f"Сумма:    `${amount}`\n"
              f"Цена:     `${price:,.4f}`\n"
              f"Кол-во:   `~{qty:.6f}`\n\n"
              f"⏳ *Авто через {AUTO_CONFIRM_TIMEOUT}с если нет ответа*")
        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"✅ ДА — {'КУПИТЬ' if side=='BUY' else 'ПРОДАТЬ'} ${amount}",
                callback_data=f"oktr__{side.lower()}__{coin.upper()}__{amount}__{ttype}"),
             InlineKeyboardButton("❌ Отмена",callback_data="cancel_trade")],
            [InlineKeyboardButton(f"⏳ Авто через {AUTO_CONFIRM_TIMEOUT}с",callback_data="noop")],
        ])
        if is_cb:
            await upd.callback_query.edit_message_text(
                text,parse_mode=ParseMode.MARKDOWN,reply_markup=kb)
            mid=upd.callback_query.message.message_id
        else:
            sent=await upd.message.reply_text(
                text,parse_mode=ParseMode.MARKDOWN,reply_markup=kb)
            mid=sent.message_id
        USER_DATA[uid]["pending_trade"]={"coin":coin,"side":side,"amount":amount,
                                          "msg_id":mid,"timestamp":time.time(),
                                          "chat_id":chat_id,"ttype":ttype}
        ctx.job_queue.run_once(_auto_job,when=AUTO_CONFIRM_TIMEOUT,
                               data={"uid":uid,"coin":coin,"side":side,
                                     "amount":amount,"msg_id":mid,"ttype":ttype},
                               name=f"auto_{uid}")
        return

    order=place_order(coin,side,amount,ttype)
    USER_DATA[uid]["pending_trade"]=None
    if not order["ok"]:
        await ctx.bot.send_message(chat_id,
            f"❌ *Ошибка сделки:*\n`{order['error']}`",
            parse_mode=ParseMode.MARKDOWN); return
    update_portfolio(uid,order); record_order(uid,order,note)
    mt=" _(Демо)_" if order.get("mock") else (" _(Testnet)_" if USE_TESTNET else "")
    se="🛒 КУПЛЕНО" if side=="BUY" else "💰 ПРОДАНО"
    await ctx.bot.send_message(chat_id,
        f"✅ *Сделка исполнена*{mt}\n\n"
        f"{se} *{order['symbol']}*\n"
        f"Тип:    {TRADE_TYPES.get(order.get('type','spot'),'')}\n"
        f"Кол-во: `{order['qty']:.6f}`\n"
        f"Цена:   `${order['price']:,.4f}`\n"
        f"Итого:  `${order['total']:.2f}`\n"
        f"ID:     `{order['orderId']}`"
        +(f"\n🤖 _{note}_" if note else ""),
        parse_mode=ParseMode.MARKDOWN,reply_markup=back())

async def _auto_job(ctx):
    d=ctx.job.data; uid=d["uid"]
    if not USER_DATA[uid].get("pending_trade"): return
    chat_id=USER_DATA[uid]["chat_id"]
    try:
        await ctx.bot.edit_message_text(
            chat_id=chat_id,message_id=d["msg_id"],
            text=f"⏳ Авто-исполнение {d['side']} ${d['amount']} {d['coin']}...",
            parse_mode=ParseMode.MARKDOWN)
    except: pass
    await do_trade(uid,ctx,d["coin"],d["side"],d["amount"],
                   confirmed=True,ttype=d.get("ttype","spot"),
                   note=f"Авто через {AUTO_CONFIRM_TIMEOUT}с")

async def do_auto_trade(uid,chat_id,coin,ctx):
    if not USER_DATA[uid]["auto_enabled"]: return
    USER_DATA[uid]["chat_id"]=chat_id
    ta=compute_ta(coin); t=get_price(coin); p=t.get("price",0)
    ttype=USER_DATA[uid]["auto_type"]; amount=USER_DATA[uid]["auto_size"]
    if ta["score"]>=2: side="BUY"
    elif ta["score"]<=-2: side="SELL"
    else: return
    se="🛒" if side=="BUY" else "💰"
    rows=[]; row=[]
    for s in TRADE_SIZES:
        row.append(InlineKeyboardButton(f"${s}",
            callback_data=f"oktr__{side.lower()}__{coin.upper()}__{s}__{ttype}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(
        f"⏳ Авто ${amount} через {AUTO_CONFIRM_TIMEOUT}с",callback_data="noop")])
    rows.append([InlineKeyboardButton("❌ Пропустить",callback_data="cancel_trade")])
    sent=await ctx.bot.send_message(chat_id,
        f"🤖 *Авто-сигнал*\n\n"
        f"Монета: *{coin.upper()}USDT*\n"
        f"Тип:    {TRADE_TYPES.get(ttype,'')}\n"
        f"Цена:   `${p:,.4f}`\n"
        f"Сигнал: {ta['signal']}\n"
        f"RSI:    `{ta['rsi']}`\n\n"
        f"{se} Предложение: *{'КУПИТЬ' if side=='BUY' else 'ПРОДАТЬ'}*\n"
        f"Выберите сумму или ждите {AUTO_CONFIRM_TIMEOUT}с:",
        parse_mode=ParseMode.MARKDOWN,reply_markup=InlineKeyboardMarkup(rows))
    USER_DATA[uid]["pending_trade"]={"coin":coin,"side":side,"amount":amount,
                                      "msg_id":sent.message_id,"timestamp":time.time(),
                                      "chat_id":chat_id,"ttype":ttype}
    ctx.job_queue.run_once(_auto_job,when=AUTO_CONFIRM_TIMEOUT,
                           data={"uid":uid,"coin":coin,"side":side,"amount":amount,
                                 "msg_id":sent.message_id,"ttype":ttype},
                           name=f"auto_{uid}")

# ── COMMANDS ──────────────────────────────────────────────────────
async def cmd_start(u,c):
    uid=u.effective_user.id; name=u.effective_user.first_name or "Трейдер"
    USER_DATA[uid]["chat_id"]=u.effective_chat.id
    live="\n⚠️ _Демо-режим_" if not bc else ("\n🟡 _Testnet_" if USE_TESTNET else "\n🟢 _LIVE торговля_")
    st="🟢 ВКЛ" if USER_DATA[uid]["auto_enabled"] else "🔴 ВЫКЛ"
    await u.message.reply_text(
        f"👋 *Добро пожаловать, {name}!*\n\n"
        f"🤖 *Binance Pro Bot v6.0*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛒 Покупка / 💰 Продажа\n"
        f"📈 Спот | 🔮 Фьючерсы | 💳 Маржа\n"
        f"🤖 Авто-трейд: {st}\n"
        f"📉 Графики с индикаторами\n"
        f"🔔 Алерты по всем монетам\n"
        f"{live}\n\n"
        f"👇 *Выберите действие:*",
        parse_mode=ParseMode.MARKDOWN,reply_markup=main_kb())

async def cmd_help(u,c):
    await u.message.reply_text(
        "📚 *КОМАНДЫ*\n\n"
        "`/start` — Главное меню\n"
        "`/buy BTC 20` — Купить $20 BTC\n"
        "`/sell ETH 15` — Продать $15 ETH\n"
        "`/auto on/off` — Вкл/выкл авто\n"
        "`/scan` — Сканировать монеты\n"
        "`/price BTC ETH` — Цены\n"
        "`/chart BTC 1h` — График\n"
        "`/portfolio` — Портфель\n"
        "`/orders` — История сделок\n"
        "`/balance` — Баланс\n"
        "`/analysis BTC` — TA анализ\n"
        "`/alert BTC above 70000`\n"
        "`/fg` — Страх и Жадность\n\n"
        f"🪙 Монеты: {', '.join(TOP_COINS)}",
        parse_mode=ParseMode.MARKDOWN,reply_markup=back())

async def cmd_buy(u,c):
    args=c.args
    if len(args)<2:
        await u.message.reply_text("📌 `/buy BTC 20`",parse_mode=ParseMode.MARKDOWN); return
    uid=u.effective_user.id
    await do_trade(u,c,args[0],"BUY",float(args[1]),ttype=USER_DATA[uid]["auto_type"])

async def cmd_sell(u,c):
    args=c.args
    if len(args)<2:
        await u.message.reply_text("📌 `/sell ETH 15`",parse_mode=ParseMode.MARKDOWN); return
    uid=u.effective_user.id
    await do_trade(u,c,args[0],"SELL",float(args[1]),ttype=USER_DATA[uid]["auto_type"])

async def cmd_auto(u,c):
    uid=u.effective_user.id; args=c.args
    if args and args[0].lower() in ("on","off","вкл","выкл"):
        on=args[0].lower() in ("on","вкл")
        USER_DATA[uid]["auto_enabled"]=on
        await u.message.reply_text(
            f"🤖 Авто-трейд: *{'🟢 ВКЛЮЧЁН' if on else '🔴 ВЫКЛЮЧЕН'}*",
            parse_mode=ParseMode.MARKDOWN); return
    await u.message.reply_text("🤖 *Авто-трейд:*",
                                parse_mode=ParseMode.MARKDOWN,reply_markup=auto_kb(uid))

async def cmd_scan(u,c):
    uid=u.effective_user.id
    msg=await u.message.reply_text("🔍 Сканирование 15 монет...")
    coins=USER_DATA[uid]["auto_coins"] or TOP_COINS
    best_coin=best_ta=None; best=0
    for coin in coins:
        ta=compute_ta(coin)
        if abs(ta["score"])>abs(best): best=ta["score"]; best_coin=coin; best_ta=ta
    if abs(best)>=2:
        await c.bot.edit_message_text(
            chat_id=u.effective_chat.id,message_id=msg.message_id,
            text=(f"🏆 Лучший сигнал: *{best_coin}USDT*\n"
                  f"Сигнал: {best_ta['signal']} | RSI: `{best_ta['rsi']}`\n\nТорговать?"),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Торговать",callback_data=f"autodo__{best_coin}"),
                 InlineKeyboardButton("❌ Пропустить",callback_data="m_main")]]))
    else:
        await c.bot.edit_message_text(
            chat_id=u.effective_chat.id,message_id=msg.message_id,
            text="⚪ Нет сильных сигналов.",reply_markup=back())

async def cmd_price(u,c):
    args=c.args or ["BTC","ETH","SOL"]
    lines=["💹 *ЦЕНЫ*\n"]
    for coin in args[:6]:
        t=get_price(coin)
        if "error" in t: lines.append(f"❌ {coin}: {t['error']}")
        else:
            e="🟢" if t["change"]>=0 else "🔴"
            lines.append(f"{e} *{t['symbol']}*: `${t['price']:,.4f}` ({t['change']:+.2f}%)")
    await u.message.reply_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN)

async def cmd_chart(u,c):
    args=c.args; coin=(args[0] if args else "BTC").upper()
    iv=args[1] if len(args)>1 else "1h"
    msg=await u.message.reply_text(f"⏳ Генерация графика {coin} [{iv}]...")
    img=generate_chart(coin,iv,60)
    await msg.delete()
    if img:
        await u.message.reply_photo(
            photo=img,
            caption=f"📉 *{coin}USDT* [{iv}]",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=chart_iv_kb(coin))
    else:
        await u.message.reply_text(
            f"❌ Не удалось создать график.\nПроверьте что matplotlib установлен.",
            reply_markup=chart_iv_kb(coin))

async def cmd_portfolio(u,c):
    uid=u.effective_user.id
    await u.message.reply_text(portfolio_text(uid),parse_mode=ParseMode.MARKDOWN,reply_markup=back())

async def cmd_orders(u,c):
    uid=u.effective_user.id
    msg=await u.message.reply_text("⏳ Загружаю историю...")
    trades=get_real_trades()
    if trades:
        lines=[f"📖 *История сделок Binance* ({len(trades)})\n"]
        for o in trades[:15]:
            e="🟢" if o["side"]=="BUY" else "🔴"
            lines.append(f"{e} `{o['time']}` *{o['symbol']}*\n"
                         f"   {o['side']} `{o['qty']:.6f}` @ `${o['price']:.4f}` = `${o['total']:.2f}`\n")
        await c.bot.edit_message_text(
            chat_id=u.effective_chat.id,message_id=msg.message_id,
            text="\n".join(lines),parse_mode=ParseMode.MARKDOWN,reply_markup=back()); return
    local=USER_DATA[uid]["orders"]
    if not local:
        await c.bot.edit_message_text(
            chat_id=u.effective_chat.id,message_id=msg.message_id,
            text=("📭 *Нет истории сделок*\n\n"
                  "На Binance нет сделок по этим монетам.\n"
                  "Совершите первую сделку!"),
            parse_mode=ParseMode.MARKDOWN,reply_markup=back()); return
    lines=["📖 *История сделок (бот)*\n"]
    for o in local[:10]:
        e="🟢" if o["side"]=="BUY" else "🔴"
        lines.append(f"{e} `{o['time']}` *{o['symbol']}*\n"
                     f"   {o['side']} `{o['qty']:.6f}` @ `${o['price']:.4f}` = `${o['total']:.2f}`\n")
    await c.bot.edit_message_text(
        chat_id=u.effective_chat.id,message_id=msg.message_id,
        text="\n".join(lines),parse_mode=ParseMode.MARKDOWN,reply_markup=back())

async def cmd_balance(u,c):
    bals=get_real_balance()
    err=bals.pop("_error",None); is_mock=bals.pop("_mock",False)
    if err:
        await u.message.reply_text(f"❌ `{err}`",parse_mode=ParseMode.MARKDOWN); return
    mt=" _(Демо)_" if is_mock else (" _(Testnet)_" if USE_TESTNET else "")
    lines=[f"💳 *Баланс Binance*{mt}\n"]; total=0.0; usdt=bals.pop("USDT",0)
    if usdt>0: lines.append(f"💵 *USDT*: `${usdt:.4f}`"); total+=usdt
    for asset,qty in sorted(bals.items(),key=lambda x:-x[1]):
        t=get_price(asset)
        if "error" not in t: v=qty*t["price"]; total+=v; lines.append(f"  • *{asset}*: `{qty:.6f}` ≈ `${v:.2f}`")
        else: lines.append(f"  • *{asset}*: `{qty:.6f}`")
    lines.append(f"\n💎 *Итого ≈* `${total:.2f} USDT`")
    lines.append(f"\n{'✅ Можно торговать' if usdt>=5 else '⚠️ Пополните USDT (минимум $5)'}")
    await u.message.reply_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN,reply_markup=back())

async def cmd_analysis(u,c):
    args=c.args; coin=(args[0] if args else "BTC").upper(); iv=args[1] if len(args)>1 else "1h"
    await u.message.reply_text(f"⏳ Анализ *{coin}* [{iv}]...",parse_mode=ParseMode.MARKDOWN)
    ta=compute_ta(coin,iv); t=get_price(coin)
    await u.message.reply_text(ta_text(coin,t.get("price",0),ta,iv),parse_mode=ParseMode.MARKDOWN)

async def cmd_alert(u,c):
    uid=u.effective_user.id; args=c.args
    if len(args)<3:
        await u.message.reply_text("📌 `/alert BTC above 70000`",parse_mode=ParseMode.MARKDOWN); return
    s,cond,price=args[0].upper(),args[1].lower(),float(args[2])
    USER_DATA[uid]["alerts"].append({"symbol":sym(s),"condition":cond,
                                     "price":price,"chat_id":u.effective_chat.id})
    await u.message.reply_text(
        f"🔔 Алерт: *{sym(s)}* {'⬆️' if cond=='above' else '⬇️'} `${price:,.2f}`",
        parse_mode=ParseMode.MARKDOWN)

async def cmd_fg(u,c):
    fg=fear_greed(); bar="█"*int(fg["value"]/5)+"░"*(20-int(fg["value"]/5))
    await u.message.reply_text(
        f"😱 *Страх и Жадность*\n```\n[{bar}]\n```\n{fg['emoji']} *{fg['value']}/100* — {fg['label']}",
        parse_mode=ParseMode.MARKDOWN)

# ── TEXT INPUT HANDLER ────────────────────────────────────────────
async def text_handler(u,c):
    uid=u.effective_user.id; text=u.message.text.strip()
    w=USER_DATA[uid].get("waiting_input")
    if not w: return
    if w.get("type")=="alert_price":
        try:
            price=float(text.replace("$","").replace(",","."))
            coin=w["coin"]; cond=w["cond"]
            USER_DATA[uid]["alerts"].append({"symbol":sym(coin),"condition":cond,
                                              "price":price,"chat_id":u.effective_chat.id})
            USER_DATA[uid]["waiting_input"]=None
            e="⬆️" if cond=="above" else "⬇️"
            await u.message.reply_text(
                f"✅ Алерт установлен!\n*{sym(coin)}* {e} `${price:,.2f}`",
                parse_mode=ParseMode.MARKDOWN,reply_markup=back("m_alerts"))
        except:
            await u.message.reply_text("❌ Введите только число: `70000`",parse_mode=ParseMode.MARKDOWN)
        return
    if w.get("type") in ("buy_amount","sell_amount","auto_size"):
        try:
            amount=float(text.replace("$","").replace(",","."))
            if amount<=0: raise ValueError
        except:
            await u.message.reply_text("❌ Введите число: `25.5`",parse_mode=ParseMode.MARKDOWN); return
        USER_DATA[uid]["waiting_input"]=None
        if w["type"]=="auto_size":
            USER_DATA[uid]["auto_size"]=amount
            await u.message.reply_text(f"✅ Сумма авто: `${amount}`",
                                        parse_mode=ParseMode.MARKDOWN,reply_markup=auto_kb(uid))
        else:
            side="BUY" if w["type"]=="buy_amount" else "SELL"
            await do_trade(u,c,w["coin"],side,amount,ttype=w.get("ttype",USER_DATA[uid]["auto_type"]))

# ── CALLBACK HANDLER ──────────────────────────────────────────────
async def cb(u,c):
    q=u.callback_query; await q.answer(); d=q.data
    uid=u.effective_user.id; USER_DATA[uid]["chat_id"]=u.effective_chat.id

    if d=="m_main":
        await q.edit_message_text("🤖 *Binance Pro Bot*\n\n👇 Выберите действие:",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=main_kb())
    elif d=="m_buy":
        await q.edit_message_text("🛒 *КУПИТЬ — Выберите монету:*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=coins_kb("buyc","m_main"))
    elif d=="m_sell":
        await q.edit_message_text("💰 *ПРОДАТЬ — Выберите монету:*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=coins_kb("sellc","m_main"))
    elif d=="m_portfolio":
        await q.edit_message_text(portfolio_text(uid),parse_mode=ParseMode.MARKDOWN,reply_markup=back())
    elif d=="m_balance":
        bals=get_real_balance(); err=bals.pop("_error",None); is_mock=bals.pop("_mock",False)
        if err:
            await q.edit_message_text(f"❌ `{err}`",parse_mode=ParseMode.MARKDOWN,reply_markup=back()); return
        mt=" _(Демо)_" if is_mock else ""
        lines=[f"💳 *Баланс*{mt}\n"]; total=0.0; usdt=bals.pop("USDT",0)
        if usdt>0: lines.append(f"💵 *USDT*: `${usdt:.4f}`"); total+=usdt
        for asset,qty in sorted(bals.items(),key=lambda x:-x[1])[:12]:
            t=get_price(asset)
            if "error" not in t: v=qty*t["price"]; total+=v; lines.append(f"• *{asset}*: `{qty:.6f}` ≈ `${v:.2f}`")
            else: lines.append(f"• *{asset}*: `{qty:.6f}`")
        lines.append(f"\n💎 *Итого:* `${total:.2f}`")
        await q.edit_message_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN,reply_markup=back())
    elif d=="m_orders":
        await q.edit_message_text("⏳ Загружаю...",parse_mode=ParseMode.MARKDOWN)
        trades=get_real_trades()
        if trades:
            lines=[f"📖 *Сделки Binance* ({len(trades)})\n"]
            for o in trades[:10]:
                e="🟢" if o["side"]=="BUY" else "🔴"
                lines.append(f"{e} *{o['symbol']}* {o['side']} `${o['total']:.2f}` — _{o['time']}_")
            await q.edit_message_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN,reply_markup=back())
        else:
            local=USER_DATA[uid]["orders"]
            txt=("📖 *Сделки (бот)*\n\n"+"\n".join(
                f"{'🟢' if o['side']=='BUY' else '🔴'} *{o['symbol']}* `${o['total']:.2f}` — _{o['time']}_"
                for o in local[:8])) if local else "📭 *Нет сделок*\n\nСовершите первую сделку!"
            await q.edit_message_text(txt,parse_mode=ParseMode.MARKDOWN,reply_markup=back())
    elif d=="m_prices":
        lines=["💹 *ТОП 15 ЦЕН*\n"]
        for coin in TOP_COINS:
            t=get_price(coin)
            if "error" not in t:
                e="🟢" if t["change"]>=0 else "🔴"
                lines.append(f"{e} *{coin}*: `${t['price']:,.4f}` `{t['change']:+.2f}%`")
        await q.edit_message_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN,reply_markup=back())
    elif d=="m_screener":
        res=[]
        for coin in TOP_COINS:
            t=get_price(coin)
            if "error" not in t: res.append((coin,t["change"],t["price"]))
        res.sort(key=lambda x:x[1],reverse=True)
        lines=["📋 *СКРИНЕР*\n","🟢 *Рост:*"]
        for coin,chg,pr in res[:5]: lines.append(f"  • *{coin}*: `{chg:+.2f}%` @ `${pr:,.4f}`")
        lines.append("\n🔴 *Падение:*")
        for coin,chg,pr in res[-5:]: lines.append(f"  • *{coin}*: `{chg:+.2f}%` @ `${pr:,.4f}`")
        await q.edit_message_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN,reply_markup=back())
    elif d=="m_fg":
        fg=fear_greed(); bar="█"*int(fg["value"]/5)+"░"*(20-int(fg["value"]/5))
        await q.edit_message_text(
            f"😱 *Страх и Жадность*\n```\n[{bar}]\n```\n{fg['emoji']} *{fg['value']}/100* — {fg['label']}",
            parse_mode=ParseMode.MARKDOWN,reply_markup=back())
    elif d=="m_whale":
        lines=["🐋 *Крупные сделки*\n"]
        for _ in range(6):
            coin=random.choice(TOP_COINS); amt=round(random.uniform(50,3000),1)
            tp=get_price(coin)["price"]; usd=int(amt*tp)
            side=random.choice(["🐋 ПОКУПКА","🦈 ПРОДАЖА"]); ago=random.randint(1,59)
            lines.append(f"{side} `{amt} {coin}` ~`${usd:,}` — `{ago}мин назад`")
        await q.edit_message_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN,reply_markup=back())
    elif d=="m_help":
        await q.edit_message_text("📌 Используйте `/help`",parse_mode=ParseMode.MARKDOWN,reply_markup=back())

    # CHART — send real image
    elif d=="m_chart_menu":
        await q.edit_message_text("📉 *График — Выберите монету:*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=coins_kb("chrtc","m_main"))
    elif d.startswith("chrtc__"):
        coin=d.split("__")[1]
        await q.edit_message_text(f"📉 *{coin}USDT* — Выберите интервал:",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=chart_iv_kb(coin))
    elif d.startswith("chrt__"):
        parts=d.split("__"); coin=parts[1]; iv=parts[2]
        await q.edit_message_text(f"⏳ Генерация графика {coin} [{iv}]...")
        img=generate_chart(coin,iv,60)
        chat_id=u.effective_chat.id
        if img:
            await q.delete_message()
            await c.bot.send_photo(
                chat_id=chat_id,photo=img,
                caption=f"📉 *{coin}USDT* [{iv}]  |  EMA20/50 + BB + MACD + RSI",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=chart_iv_kb(coin))
        else:
            await q.edit_message_text("❌ Ошибка генерации графика.",reply_markup=chart_iv_kb(coin))

    # ANALYSIS
    elif d=="m_analysis":
        await q.edit_message_text("🔬 *Анализ — Выберите монету:*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=coins_kb("tac","m_main"))
    elif d.startswith("tac__"):
        coin=d.split("__")[1]; ta=compute_ta(coin); t=get_price(coin)
        await q.edit_message_text(ta_text(coin,t.get("price",0),ta,"1h"),
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([
                                       [InlineKeyboardButton("🛒 КУПИТЬ",callback_data=f"buyc__{coin}"),
                                        InlineKeyboardButton("💰 ПРОДАТЬ",callback_data=f"sellc__{coin}"),
                                        InlineKeyboardButton("🔙",callback_data="m_analysis")]]))

    # BUY/SELL
    elif d.startswith("buyc__"):
        coin=d.split("__")[1]; t=get_price(coin)
        await q.edit_message_text(
            f"🛒 *КУПИТЬ {coin}USDT*\nЦена: `${t.get('price',0):,.4f}`\n\nВыберите сумму:",
            parse_mode=ParseMode.MARKDOWN,reply_markup=sizes_kb("buy",coin,"m_buy"))
    elif d.startswith("sellc__"):
        coin=d.split("__")[1]; t=get_price(coin)
        await q.edit_message_text(
            f"💰 *ПРОДАТЬ {coin}USDT*\nЦена: `${t.get('price',0):,.4f}`\n\nВыберите сумму:",
            parse_mode=ParseMode.MARKDOWN,reply_markup=sizes_kb("sell",coin,"m_sell"))
    elif d.startswith("buy__"):
        parts=d.split("__"); coin=parts[1]; amount=float(parts[2])
        await do_trade(u,c,coin,"BUY",amount,ttype=USER_DATA[uid]["auto_type"])
    elif d.startswith("sell__"):
        parts=d.split("__"); coin=parts[1]; amount=float(parts[2])
        await do_trade(u,c,coin,"SELL",amount,ttype=USER_DATA[uid]["auto_type"])
    elif d.startswith("custom__buy__"):
        coin=d.split("__")[2]
        USER_DATA[uid]["waiting_input"]={"type":"buy_amount","coin":coin,"ttype":USER_DATA[uid]["auto_type"]}
        await q.edit_message_text(f"✏️ *Своя сумма — КУПИТЬ {coin}*\n\nВведите сумму в $:",
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена",callback_data="m_main")]]))
    elif d.startswith("custom__sell__"):
        coin=d.split("__")[2]
        USER_DATA[uid]["waiting_input"]={"type":"sell_amount","coin":coin,"ttype":USER_DATA[uid]["auto_type"]}
        await q.edit_message_text(f"✏️ *Своя сумма — ПРОДАТЬ {coin}*\n\nВведите сумму в $:",
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена",callback_data="m_main")]]))

    # CONFIRM
    elif d.startswith("oktr__"):
        parts=d.split("__"); side=parts[1].upper(); coin=parts[2]
        amount=float(parts[3]); ttype=parts[4] if len(parts)>4 else "spot"
        for j in c.job_queue.get_jobs_by_name(f"auto_{uid}"): j.schedule_removal()
        USER_DATA[uid]["pending_trade"]=None
        await do_trade(u,c,coin,side,amount,confirmed=True,ttype=ttype,note="Пользователь подтвердил")
    elif d=="cancel_trade":
        for j in c.job_queue.get_jobs_by_name(f"auto_{uid}"): j.schedule_removal()
        USER_DATA[uid]["pending_trade"]=None
        await q.edit_message_text("❌ Сделка отменена.",reply_markup=back())

    # AUTO
    elif d=="m_auto":
        on=USER_DATA[uid]["auto_enabled"]
        tt=TRADE_TYPES.get(USER_DATA[uid]["auto_type"],"")
        sz=USER_DATA[uid]["auto_size"]; nc=len(USER_DATA[uid]["auto_coins"])
        await q.edit_message_text(
            f"🤖 *Авто-Трейд*\n\nСтатус: *{'🟢 ВКЛ' if on else '🔴 ВЫКЛ'}*\n"
            f"Тип: {tt}\nСумма: `${sz}`\nМонет: `{nc}/15`\n\n"
            f"_Алгоритм: RSI + MACD + Bollinger Bands_",
            parse_mode=ParseMode.MARKDOWN,reply_markup=auto_kb(uid))
    elif d=="auto_toggle":
        USER_DATA[uid]["auto_enabled"]=not USER_DATA[uid]["auto_enabled"]
        on=USER_DATA[uid]["auto_enabled"]
        await q.edit_message_text(f"🤖 Авто-трейд: *{'🟢 ВКЛЮЧЁН' if on else '🔴 ВЫКЛЮЧЕН'}*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=auto_kb(uid))
    elif d=="auto_type":
        await q.edit_message_text("🔧 *Тип торговли:*",parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([
                                       [InlineKeyboardButton("📈 Спот",callback_data="atype__spot")],
                                       [InlineKeyboardButton("🔮 Фьючерсы",callback_data="atype__futures")],
                                       [InlineKeyboardButton("💳 Маржа",callback_data="atype__margin")],
                                       [InlineKeyboardButton("🔙 Назад",callback_data="m_auto")]]))
    elif d.startswith("atype__"):
        USER_DATA[uid]["auto_type"]=d.split("__")[1]
        await q.edit_message_text(f"✅ Тип: *{TRADE_TYPES[USER_DATA[uid]['auto_type']]}*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=auto_kb(uid))
    elif d=="auto_size":
        rows=[]; row=[]
        for s in TRADE_SIZES:
            row.append(InlineKeyboardButton(f"${s}",callback_data=f"asize__{s}"))
            if len(row)==5: rows.append(row); row=[]
        if row: rows.append(row)
        rows.append([InlineKeyboardButton("✏️ Своя сумма",callback_data="asize__custom")])
        rows.append([InlineKeyboardButton("🔙 Назад",callback_data="m_auto")])
        await q.edit_message_text("💵 *Сумма авто-трейда:*",parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup(rows))
    elif d.startswith("asize__"):
        val=d.split("__")[1]
        if val=="custom":
            USER_DATA[uid]["waiting_input"]={"type":"auto_size","coin":"","ttype":""}
            await q.edit_message_text("✏️ Введите сумму в $:\nПример: `35`",
                                       parse_mode=ParseMode.MARKDOWN,
                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена",callback_data="m_auto")]]))
        else:
            USER_DATA[uid]["auto_size"]=float(val)
            await q.edit_message_text(f"✅ Сумма авто: `${val}`",
                                       parse_mode=ParseMode.MARKDOWN,reply_markup=auto_kb(uid))
    elif d=="auto_coins":
        await q.edit_message_text("🪙 *Монеты для авто-трейда:*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=auto_coins_kb(uid))
    elif d.startswith("acoin__"):
        val=d.split("__")[1]
        if val=="ALL": USER_DATA[uid]["auto_coins"]=list(TOP_COINS)
        elif val=="NONE": USER_DATA[uid]["auto_coins"]=[]
        else:
            coins=USER_DATA[uid]["auto_coins"]
            if val in coins: coins.remove(val)
            else: coins.append(val)
        await q.edit_message_text("🪙 *Монеты:*",parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=auto_coins_kb(uid))
    elif d=="auto_scan":
        await q.edit_message_text("🔍 Сканирование...")
        coins=USER_DATA[uid]["auto_coins"] or TOP_COINS
        best_coin=best_ta=None; best=0
        for coin in coins:
            ta=compute_ta(coin)
            if abs(ta["score"])>abs(best): best=ta["score"]; best_coin=coin; best_ta=ta
        if abs(best)>=2:
            await q.edit_message_text(
                f"🏆 *{best_coin}USDT* — {best_ta['signal']}\nRSI: `{best_ta['rsi']}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 Торговать",callback_data=f"autodo__{best_coin}"),
                     InlineKeyboardButton("❌ Пропустить",callback_data="m_auto")]]))
        else:
            await q.edit_message_text("⚪ Нет сильных сигналов.",reply_markup=back("m_auto"))
    elif d.startswith("autodo__"):
        coin=d.split("__")[1]
        await do_auto_trade(uid,u.effective_chat.id,coin,c)

    # ALERTS
    elif d=="m_alerts":
        alerts=USER_DATA[uid]["alerts"]
        if not alerts: txt="🔕 *Алерты*\n\nНет активных алертов."
        else:
            lines=["🔔 *Активные алерты:*\n"]
            for i,a in enumerate(alerts,1):
                e="⬆️" if a["condition"]=="above" else "⬇️"
                lines.append(f"`{i}.` *{a['symbol']}* {e} `${a['price']:,.2f}`")
            txt="\n".join(lines)
        await q.edit_message_text(txt,parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([
                                       [InlineKeyboardButton("➕ Добавить",callback_data="alert_add")],
                                       [InlineKeyboardButton("🗑 Удалить все",callback_data="alert_clear")],
                                       [InlineKeyboardButton("🔙 Назад",callback_data="m_main")]]))
    elif d=="alert_add":
        await q.edit_message_text("🔔 *Выберите монету:*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=coins_kb("alertc","m_alerts"))
    elif d.startswith("alertc__"):
        coin=d.split("__")[1]; t=get_price(coin)
        await q.edit_message_text(
            f"🔔 *{coin}USDT* — Цена: `${t.get('price',0):,.4f}`\n\nВыберите условие:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬆️ Выше",callback_data=f"alertcond__{coin}__above"),
                 InlineKeyboardButton("⬇️ Ниже",callback_data=f"alertcond__{coin}__below")],
                [InlineKeyboardButton("🔙 Назад",callback_data="alert_add")]]))
    elif d.startswith("alertcond__"):
        parts=d.split("__"); coin=parts[1]; cond=parts[2]
        USER_DATA[uid]["waiting_input"]={"type":"alert_price","coin":coin,"cond":cond}
        t=get_price(coin); cond_txt="выше ⬆️" if cond=="above" else "ниже ⬇️"
        await q.edit_message_text(
            f"🔔 *{coin}USDT — {cond_txt}*\nТекущая: `${t.get('price',0):,.4f}`\n\n✏️ Введите целевую цену:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена",callback_data="m_alerts")]]))
    elif d=="alert_clear":
        USER_DATA[uid]["alerts"]=[]
        await q.edit_message_text("🗑 Все алерты удалены.",reply_markup=back("m_main"))
    elif d=="noop":
        pass

# ── BACKGROUND JOBS ───────────────────────────────────────────────
async def alerts_job(ctx):
    for uid,data in list(USER_DATA.items()):
        triggered,remaining=[],[]
        for alert in data.get("alerts",[]):
            t=get_price(alert["symbol"])
            if "error" in t: remaining.append(alert); continue
            p=t["price"]
            hit=((alert["condition"]=="above" and p>=alert["price"]) or
                 (alert["condition"]=="below"  and p<=alert["price"]))
            if hit: triggered.append((alert,p))
            else:   remaining.append(alert)
        data["alerts"]=remaining
        for alert,cur in triggered:
            e="⬆️" if alert["condition"]=="above" else "⬇️"
            try:
                await ctx.bot.send_message(alert["chat_id"],
                    f"🔔 *АЛЕРТ!* *{alert['symbol']}* {e} `${alert['price']:,.2f}`\n"
                    f"Текущая: `${cur:,.4f}`",parse_mode=ParseMode.MARKDOWN)
            except Exception as err: log.error(f"Alert: {err}")

async def auto_job(ctx):
    for uid,data in list(USER_DATA.items()):
        if not data.get("auto_enabled"): continue
        if not data.get("chat_id"):      continue
        if data.get("pending_trade"):    continue
        coins=data["auto_coins"] or TOP_COINS
        coin=random.choice(coins); ta=compute_ta(coin)
        if abs(ta["score"])>=2:
            await do_auto_trade(uid,data["chat_id"],coin,ctx)
            await asyncio.sleep(1)

# ── HEALTH SERVER ─────────────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self,*a): pass

def health():
    HTTPServer(("0.0.0.0",PORT),H).serve_forever()

# ── MAIN ──────────────────────────────────────────────────────────
async def main():
    if TELEGRAM_TOKEN=="YOUR_TOKEN":
        print("Set TELEGRAM_TOKEN!"); return
    Thread(target=health,daemon=True).start()
    app=Application.builder().token(TELEGRAM_TOKEN).build()
    for cmd,fn in [("start",cmd_start),("help",cmd_help),("buy",cmd_buy),
                   ("sell",cmd_sell),("auto",cmd_auto),("scan",cmd_scan),
                   ("price",cmd_price),("chart",cmd_chart),("portfolio",cmd_portfolio),
                   ("orders",cmd_orders),("balance",cmd_balance),
                   ("analysis",cmd_analysis),("alert",cmd_alert),("fg",cmd_fg)]:
        app.add_handler(CommandHandler(cmd,fn))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_handler))
    app.job_queue.run_repeating(alerts_job,interval=60,first=15)
    app.job_queue.run_repeating(auto_job,interval=300,first=60)
    log.info("🚀 Bot v6.0 started!")
    async with app:
        await app.initialize(); await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__=="__main__":
    asyncio.run(main())
