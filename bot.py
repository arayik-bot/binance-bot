"""
BINANCE PRO TRADING BOT v4.0
Russian UI | Spot+Futures+Margin | Real Portfolio | Chart | Auto Trade
Deploy: Render.com | Python 3.14+
"""

import os, asyncio, logging, time, math, random
from datetime import datetime
from typing import Optional
from collections import defaultdict
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
    BINANCE_OK = True
except ImportError:
    BINANCE_OK = False

logging.basicConfig(format="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S", level=logging.INFO)
log = logging.getLogger("Bot")

# 鈹€鈹€ CONFIG 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
TELEGRAM_TOKEN       = os.environ.get("TELEGRAM_TOKEN",  "YOUR_TOKEN")
BINANCE_API_KEY      = os.environ.get("BINANCE_API_KEY", "")
BINANCE_SECRET       = os.environ.get("BINANCE_SECRET",  "")
ADMIN_IDS            = list(map(int, os.environ.get("ADMIN_IDS", "0").split(",")))
USE_TESTNET          = os.environ.get("USE_TESTNET", "false").lower() == "true"
PORT                 = int(os.environ.get("PORT", 8080))
AUTO_CONFIRM_TIMEOUT = int(os.environ.get("AUTO_CONFIRM_TIMEOUT", "30"))

TRADE_SIZES = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
TOP_COINS   = ["BTC","ETH","BNB","SOL","XRP","ADA","DOGE","AVAX","DOT","MATIC","LINK","LTC","UNI","ATOM","NEAR"]
TRADE_TYPES = {"spot": "馃搱 小锌芯褌", "futures": "馃敭 肖褜褞褔械褉褋褘", "margin": "馃挸 袦邪褉卸邪"}

# 鈹€鈹€ STATE 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def default_user():
    return {
        "portfolio": {}, "alerts": [], "orders": [],
        "pending_trade": None, "chat_id": None,
        "auto_enabled": False, "auto_coins": list(TOP_COINS),
        "auto_type": "spot", "auto_size": 20,
        "waiting_input": None,
    }

USER_DATA = defaultdict(default_user)

# 鈹€鈹€ BINANCE 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
bc = None
if BINANCE_OK and BINANCE_API_KEY:
    try:
        bc = Client(BINANCE_API_KEY, BINANCE_SECRET, testnet=USE_TESTNET)
        log.info("鉁� Binance " + ("TESTNET" if USE_TESTNET else "LIVE"))
    except Exception as e:
        log.warning(f"Binance: {e}")

MOCK = {
    "BTCUSDT":67500,"ETHUSDT":3450,"BNBUSDT":582,"SOLUSDT":176,"XRPUSDT":0.58,
    "ADAUSDT":0.48,"DOGEUSDT":0.162,"AVAXUSDT":38.7,"DOTUSDT":7.8,"MATICUSDT":0.91,
    "LINKUSDT":18.4,"LTCUSDT":82.0,"UNIUSDT":9.3,"ATOMUSDT":10.5,"NEARUSDT":7.1,
}

def sym(coin):
    c = coin.upper().strip()
    return c if c.endswith("USDT") else c + "USDT"

def get_price(coin):
    s = sym(coin)
    if bc:
        try:
            t = bc.get_ticker(symbol=s)
            return {"symbol":s,"price":float(t["lastPrice"]),"change":float(t["priceChangePercent"]),
                    "high":float(t["highPrice"]),"low":float(t["lowPrice"]),"volume":float(t["volume"])}
        except Exception as e:
            return {"error":str(e),"symbol":s}
    base = MOCK.get(s, 10.0) * random.uniform(0.98, 1.02)
    return {"symbol":s,"price":round(base,6),"change":round(random.uniform(-6,6),2),
            "high":round(base*1.04,6),"low":round(base*0.96,6),"volume":round(random.uniform(5000,500000),2)}

def get_klines(coin, interval="1h", limit=30):
    s = sym(coin)
    if bc:
        try:
            return bc.get_klines(symbol=s, interval=interval, limit=limit)
        except:
            pass
    base = MOCK.get(s, 50.0)
    data = []; t = int(time.time()*1000) - limit*3600000
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
                    for b in acc["balances"] if float(b["free"])+float(b["locked"])>0.000001}
        except Exception as e:
            return {"error": str(e)}
    return {"USDT":1000.0,"BTC":0.01,"ETH":0.5,"mock":True}

def get_real_trades():
    """Fetch real trades from Binance for all TOP_COINS."""
    if not bc:
        return []
    all_trades = []
    for coin in TOP_COINS:
        s = sym(coin)
        try:
            trades = bc.get_my_trades(symbol=s, limit=5)
            for t in trades:
                all_trades.append({
                    "time":    datetime.fromtimestamp(t["time"]/1000).strftime("%d.%m %H:%M"),
                    "symbol":  s,
                    "side":    "BUY" if t["isBuyer"] else "SELL",
                    "qty":     float(t["qty"]),
                    "price":   float(t["price"]),
                    "total":   float(t["qty"])*float(t["price"]),
                    "ts":      t["time"],
                })
        except:
            continue
    all_trades.sort(key=lambda x: x["ts"], reverse=True)
    return all_trades

def place_order(coin, side, amount, trade_type="spot"):
    s = sym(coin); ticker = get_price(coin)
    if "error" in ticker:
        return {"ok":False,"error":ticker["error"]}
    price = ticker["price"]; qty = amount/price
    if bc:
        try:
            if trade_type == "futures":
                order = bc.futures_create_order(symbol=s,side=side,type="MARKET",
                    quoteOrderQty=amount) if side=="BUY" else \
                    bc.futures_create_order(symbol=s,side=side,type="MARKET",quantity=f"{qty:.6f}")
            elif trade_type == "margin":
                order = bc.create_margin_order(symbol=s,side=side,type="MARKET",
                    quoteOrderQty=amount) if side=="BUY" else \
                    bc.create_margin_order(symbol=s,side=side,type="MARKET",quantity=f"{qty:.6f}")
            else:
                order = bc.order_market_buy(symbol=s,quoteOrderQty=amount) if side=="BUY" else \
                        bc.order_market_sell(symbol=s,quantity=f"{qty:.6f}")
            fills = order.get("fills",[{}])
            fp = float(fills[0].get("price",price)) if fills else price
            fq = float(order.get("executedQty",qty))
            return {"ok":True,"symbol":s,"side":side,"qty":fq,"price":fp,
                    "total":fq*fp,"orderId":order.get("orderId"),"type":trade_type,"mock":False}
        except BinanceAPIException as e:
            return {"ok":False,"error":f"Binance: {e.message}"}
        except Exception as e:
            return {"ok":False,"error":str(e)}
    ep = price*random.uniform(0.999,1.001); eq = amount/ep
    return {"ok":True,"symbol":s,"side":side,"qty":round(eq,8),"price":round(ep,4),
            "total":round(amount,2),"orderId":f"DEMO-{int(time.time())}","type":trade_type,"mock":True}

# 鈹€鈹€ TECHNICAL ANALYSIS 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def compute_ta(coin, interval="1h"):
    klines = get_klines(coin, interval, 120)
    closes = [float(k[4]) for k in klines]

    def ema(p, n):
        k=2/(n+1); r=[sum(p[:n])/n]
        for x in p[n:]: r.append(x*k+r[-1]*(1-k))
        return r

    def rsi(p, n=14):
        g,l=[],[]
        for i in range(1,len(p)):
            d=p[i]-p[i-1]; g.append(max(d,0)); l.append(max(-d,0))
        ag=sum(g[-n:])/n; al=sum(l[-n:])/n
        return round(100-100/(1+ag/al),2) if al else 100.0

    e12=ema(closes,12); e26=ema(closes,26)
    n=min(len(e12),len(e26)); ml=[e12[-n+i]-e26[i] for i in range(n)]
    hist=ml[-1]-ema(ml,9)[-1]
    p20=closes[-20:]; sma=sum(p20)/20
    std=math.sqrt(sum((c-sma)**2 for c in p20)/20)
    rsi_v=rsi(closes); cur=closes[-1]; score=0

    if rsi_v<30:      score+=2
    elif rsi_v>70:    score-=2
    if hist>0:        score+=1
    else:             score-=1
    if cur<sma-2*std: score+=1
    elif cur>sma+2*std: score-=1
    if e12[-1]>e26[-1]: score+=1
    else:               score-=1

    if score>=3:    sig="馃煝 小袠袥鞋袧袗携 袩袨袣校袩袣袗"
    elif score>=1:  sig="馃煩 袩袨袣校袩袣袗"
    elif score<=-3: sig="馃敶 小袠袥鞋袧袗携 袩袪袨袛袗袞袗"
    elif score<=-1: sig="馃煡 袩袪袨袛袗袞袗"
    else:           sig="馃煛 袧袝袡孝袪袗袥鞋袧袨"

    return {"rsi":rsi_v,"hist":round(hist,4),"signal":sig,"score":score,
            "bb_u":round(sma+2*std,4),"bb_l":round(sma-2*std,4),"bb_m":round(sma,4),
            "ema12":round(e12[-1],4),"ema26":round(e26[-1],4)}

def ascii_chart(coin, interval="1h", bars=28):
    klines=get_klines(coin,interval,bars)
    closes=[float(k[4]) for k in klines]; opens=[float(k[1]) for k in klines]
    highs=[float(k[2]) for k in klines]; lows=[float(k[3]) for k in klines]
    hi=max(highs); lo=min(lows); span=hi-lo or 1; rows=12; result=[]
    for row in range(rows,-1,-1):
        level=lo+span*row/rows; lb=f"{level:>9.2f}|"; line=""
        for i in range(len(closes)):
            bh=max(closes[i],opens[i]); bl=min(closes[i],opens[i])
            bull=closes[i]>=opens[i]
            ch=lo+span*(row+0.5)/rows; cl=lo+span*(row-0.5)/rows
            if bl<=ch and bh>=cl: line+="#" if bull else "-"
            elif lows[i]<=ch and highs[i]>=cl: line+="|"
            else: line+=" "
        result.append(lb+line)
    result.append(" "*10+"+"+"-"*len(closes))
    last=closes[-1]; chg=((last-closes[0])/closes[0]*100) if closes[0] else 0
    result.append(f"  {last:,.4f}  {'+'if chg>=0 else ''}{chg:.2f}%")
    return "\n".join(result)

def fear_greed():
    v=random.randint(18,88)
    lb=("袣褉邪泄薪懈泄 褋褌褉邪褏","小褌褉邪褏","袧械泄褌褉邪谢褜薪芯","袞邪写薪芯褋褌褜","袣褉邪泄薪褟褟 卸邪写薪芯褋褌褜")[0 if v<25 else 1 if v<45 else 2 if v<55 else 3 if v<75 else 4]
    em=("馃槺","馃槰","馃槓","馃槒","馃")[0 if v<25 else 1 if v<45 else 2 if v<55 else 3 if v<75 else 4]
    return {"value":v,"label":lb,"emoji":em}

# 鈹€鈹€ PORTFOLIO 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def portfolio_text(uid):
    lines=["馃捈 *袩袨袪孝肖袝袥鞋*\n"]; ti=tc=0.0
    bals=get_real_balance()

    if "error" in bals:
        lines.append(f"鉂� 袨褕懈斜泻邪: {bals['error']}")
        return "\n".join(lines)

    is_mock = bals.pop("mock", False)
    if is_mock:
        lines.append("_(袛械屑芯-写邪薪薪褘械 鈥� 锌芯写泻谢褞褔懈褌械 Binance API)_\n")

    has_assets = False
    usdt = bals.pop("USDT", 0)

    for asset, qty in sorted(bals.items(), key=lambda x:-x[1]):
        if qty < 0.000001: continue
        t=get_price(asset)
        if "error" in t: continue
        p=t["price"]; val=qty*p; tc+=val; has_assets=True
        local=USER_DATA[uid]["portfolio"].get(asset+"USDT")
        if local and local.get("avg_price"):
            avg=local["avg_price"]; inv=qty*avg; pnl=val-inv
            pct=pnl/inv*100 if inv else 0; ti+=inv
            e="馃煝" if pnl>=0 else "馃敶"
            lines.append(f"{e} *{asset}*: `{qty:.6f}`\n"
                         f"   笑械薪邪 `${p:.4f}` | 小褌芯懈屑. `${val:.2f}`\n"
                         f"   PnL `{'+' if pnl>=0 else ''}{pnl:.2f}$` ({pct:+.1f}%)\n")
        else:
            lines.append(f"馃挔 *{asset}*: `{qty:.6f}`\n"
                         f"   笑械薪邪 `${p:.4f}` | 小褌芯懈屑. `${val:.2f}`\n")

    if usdt > 0:
        lines.append(f"馃挼 *USDT*: `${usdt:.4f}`")
        tc += usdt

    if not has_assets and usdt == 0:
        return "馃搨 袘邪谢邪薪褋 锌褍褋褌.\n袩芯锌芯谢薪懈褌械 褋褔褢褌 写谢褟 褌芯褉谐芯胁谢懈."

    lines.append("鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€")
    lines.append(f"馃拵 *袨斜褖邪褟 褋褌芯懈屑芯褋褌褜:* `${tc:.2f} USDT`")
    if ti>0:
        tp=tc-ti; te="馃煝" if tp>=0 else "馃敶"
        lines.append(f"{te} *PnL:* `{'+' if tp>=0 else ''}{tp:.2f}$` ({tp/ti*100:+.1f}%)")
    return "\n".join(lines)

def update_portfolio(uid, order):
    s=order["symbol"]; qty=order["qty"]; p=order["price"]
    port=USER_DATA[uid]["portfolio"]
    if order["side"]=="BUY":
        if s in port:
            oq=port[s]["qty"]; oa=port[s]["avg_price"]
            nq=oq+qty; port[s]={"qty":nq,"avg_price":round((oq*oa+qty*p)/nq,6)}
        else:
            port[s]={"qty":qty,"avg_price":p}
    else:
        if s in port:
            nq=port[s]["qty"]-qty
            if nq<=0.000001: del port[s]
            else: port[s]["qty"]=round(nq,8)

def record_order(uid, order, note=""):
    USER_DATA[uid]["orders"].insert(0,{
        "time":datetime.now().strftime("%d.%m %H:%M"),
        "symbol":order["symbol"],"side":order["side"],
        "qty":order["qty"],"price":order["price"],
        "total":order["total"],"orderId":order.get("orderId",""),
        "type":order.get("type","spot"),"note":note
    })
    USER_DATA[uid]["orders"]=USER_DATA[uid]["orders"][:50]

# 鈹€鈹€ KEYBOARDS 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("馃洅 袣褍锌懈褌褜",      callback_data="m_buy"),
         InlineKeyboardButton("馃挵 袩褉芯写邪褌褜",     callback_data="m_sell")],
        [InlineKeyboardButton("馃 袗胁褌芯-褌褉械泄写",  callback_data="m_auto"),
         InlineKeyboardButton("馃捈 袩芯褉褌褎械谢褜",    callback_data="m_portfolio")],
        [InlineKeyboardButton("馃搳 袗薪邪谢懈蟹",      callback_data="m_analysis"),
         InlineKeyboardButton("馃搲 袚褉邪褎懈泻",      callback_data="m_chart")],
        [InlineKeyboardButton("馃捁 笑械薪褘",        callback_data="m_prices"),
         InlineKeyboardButton("馃搵 小泻褉懈薪械褉",     callback_data="m_screener")],
        [InlineKeyboardButton("馃敂 袗谢械褉褌褘",      callback_data="m_alerts"),
         InlineKeyboardButton("馃摉 小写械谢泻懈",      callback_data="m_orders")],
        [InlineKeyboardButton("馃槺 小褌褉邪褏/袞邪写薪.", callback_data="m_fg"),
         InlineKeyboardButton("馃悑 袣懈褌褘",        callback_data="m_whale")],
        [InlineKeyboardButton("馃挸 袘邪谢邪薪褋",      callback_data="m_balance"),
         InlineKeyboardButton("鈩癸笍 袩芯屑芯褖褜",       callback_data="m_help")],
    ])

def back(t="m_main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("馃敊 袧邪蟹邪写",callback_data=t)]])

def coins_kb(act, back_cb="m_main"):
    rows=[]; row=[]
    for c in TOP_COINS:
        row.append(InlineKeyboardButton(c, callback_data=f"{act}_{c}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("馃敊 袧邪蟹邪写",callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)

def sizes_kb(act, coin, back_cb):
    rows=[]; row=[]
    for s in TRADE_SIZES:
        row.append(InlineKeyboardButton(f"${s}", callback_data=f"{act}_{coin}_{s}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("鉁忥笍 小胁芯褟 褋褍屑屑邪", callback_data=f"custom_{act}_{coin}")])
    rows.append([InlineKeyboardButton("馃敊 袧邪蟹邪写", callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)

def auto_kb(uid):
    st="馃煝 袙袣袥" if USER_DATA[uid]["auto_enabled"] else "馃敶 袙蝎袣袥"
    tt=TRADE_TYPES.get(USER_DATA[uid]["auto_type"],"")
    sz=USER_DATA[uid]["auto_size"]
    nc=len(USER_DATA[uid]["auto_coins"])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"袗胁褌芯-褌褉械泄写: {st}", callback_data="noop")],
        [InlineKeyboardButton("鈻讹笍 袙泻谢褞褔懈褌褜" if not USER_DATA[uid]["auto_enabled"] else "鈴� 袙褘泻谢褞褔懈褌褜",
                              callback_data="auto_toggle")],
        [InlineKeyboardButton(f"孝懈锌: {tt}",     callback_data="auto_type")],
        [InlineKeyboardButton(f"小褍屑屑邪: ${sz}",  callback_data="auto_size")],
        [InlineKeyboardButton(f"袦芯薪械褌褘: {nc}/15", callback_data="auto_coins")],
        [InlineKeyboardButton("馃攳 小泻邪薪懈褉芯胁邪褌褜", callback_data="auto_scan")],
        [InlineKeyboardButton("馃敊 袧邪蟹邪写",        callback_data="m_main")],
    ])

def auto_coins_kb(uid):
    sel=USER_DATA[uid]["auto_coins"]; rows=[]; row=[]
    for c in TOP_COINS:
        ch="鉁�" if c in sel else "鈼伙笍"
        row.append(InlineKeyboardButton(f"{ch}{c}", callback_data=f"acoin_{c}"))
        if len(row)==3: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("鉁� 袙褋械",callback_data="acoin_all"),
                 InlineKeyboardButton("鉂� 小斜褉芯褋",callback_data="acoin_none")])
    rows.append([InlineKeyboardButton("馃敊 袧邪蟹邪写",callback_data="m_auto")])
    return InlineKeyboardMarkup(rows)

def chart_kb(coin):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(iv, callback_data=f"chart_{coin}_{iv}")
         for iv in ["15m","1h","4h","1d","1w"]],
        [InlineKeyboardButton("馃敊 袧邪蟹邪写", callback_data="m_chart")]
    ])

def ta_text(coin, price, ta, iv):
    re="馃煝" if ta["rsi"]<30 else ("馃敶" if ta["rsi"]>70 else "馃煛")
    me="馃煝" if ta["hist"]>0 else "馃敶"
    return (f"馃敩 *袗薪邪谢懈蟹 {coin}USDT [{iv}]*\n\n"
            f"馃挼 笑械薪邪: `${price:,.4f}`\n\n"
            f"馃搲 *RSI(14):* {re} `{ta['rsi']}`\n"
            f"   {'袩械褉械锌褉芯写邪薪 馃敟' if ta['rsi']<30 else ('袩械褉械泻褍锌谢械薪 鉂勶笍' if ta['rsi']>70 else '袧芯褉屑邪')}\n\n"
            f"馃搳 *MACD:* {me} hist=`{ta['hist']}`\n\n"
            f"馃搹 *Bollinger:*\n"
            f"   袙械褉褏 `{ta['bb_u']}` | 小械褉械写懈薪邪 `{ta['bb_m']}` | 袧懈蟹 `{ta['bb_l']}`\n\n"
            f"馃搻 *EMA 12/26:* `{ta['ema12']}` / `{ta['ema26']}`\n\n"
            f"鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣\n"
            f"馃幆 小懈谐薪邪谢: {ta['signal']}\n"
            f"馃搶 袨褑械薪泻邪: `{ta['score']}/4`")

# 鈹€鈹€ TRADE CORE 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
async def do_trade(source, ctx, coin, side, amount, confirmed=False, ttype="spot", note=""):
    if isinstance(source, int):
        uid=source; chat_id=USER_DATA[uid]["chat_id"]; is_cb=False; upd=None
    else:
        upd=source; uid=upd.effective_user.id
        chat_id=upd.effective_chat.id
        is_cb=upd.callback_query is not None
        USER_DATA[uid]["chat_id"]=chat_id

    t=get_price(coin)
    if "error" in t:
        msg=f"鉂� 袧械褌 褑械薪褘 写谢褟 {coin}: {t['error']}"
        if is_cb: await upd.callback_query.edit_message_text(msg)
        elif upd: await upd.message.reply_text(msg)
        return

    price=t["price"]; qty=amount/price

    if not confirmed:
        se="馃洅" if side=="BUY" else "馃挵"
        text=(f"{se} *袩芯写褌胁械褉写懈褌褜 褋写械谢泻褍*\n\n"
              f"袦芯薪械褌邪:  *{sym(coin)}*\n"
              f"袛械泄褋褌胁懈械: *{'袣校袩袠孝鞋' if side=='BUY' else '袩袪袨袛袗孝鞋'}*\n"
              f"孝懈锌:     {TRADE_TYPES.get(ttype,'小锌芯褌')}\n"
              f"小褍屑屑邪:   `${amount}`\n"
              f"笑械薪邪:    `${price:,.4f}`\n"
              f"袣芯谢-胁芯:  `~{qty:.6f}`\n\n"
              f"鈴� *袗胁褌芯 褔械褉械蟹 {AUTO_CONFIRM_TIMEOUT}褋 械褋谢懈 薪械褌 芯褌胁械褌邪*")
        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"鉁� 袛袗 鈥� {'袣校袩袠孝鞋' if side=='BUY' else '袩袪袨袛袗孝鞋'} ${amount}",
                                  callback_data=f"ok_{side.lower()}_{coin.upper()}_{amount}_{ttype}"),
             InlineKeyboardButton("鉂� 袨褌屑械薪邪", callback_data="cancel_trade")],
            [InlineKeyboardButton(f"鈴� 袗胁褌芯 褔械褉械蟹 {AUTO_CONFIRM_TIMEOUT}褋", callback_data="noop")],
        ])
        if is_cb:
            await upd.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            mid=upd.callback_query.message.message_id
        else:
            sent=await upd.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            mid=sent.message_id
        USER_DATA[uid]["pending_trade"]={"coin":coin,"side":side,"amount":amount,
                                          "msg_id":mid,"timestamp":time.time(),
                                          "chat_id":chat_id,"ttype":ttype}
        ctx.job_queue.run_once(_auto_job, when=AUTO_CONFIRM_TIMEOUT,
                               data={"uid":uid,"coin":coin,"side":side,"amount":amount,
                                     "msg_id":mid,"ttype":ttype},
                               name=f"auto_{uid}")
        return

    order=place_order(coin, side, amount, ttype)
    USER_DATA[uid]["pending_trade"]=None
    if not order["ok"]:
        await ctx.bot.send_message(chat_id, f"鉂� 袨褕懈斜泻邪:\n`{order['error']}`", parse_mode=ParseMode.MARKDOWN)
        return
    update_portfolio(uid, order); record_order(uid, order, note)
    mt=" _(袛械屑芯)_" if order.get("mock") else (" _(Testnet)_" if USE_TESTNET else "")
    se="馃洅 袣校袩袥袝袧袨" if side=="BUY" else "馃挵 袩袪袨袛袗袧袨"
    await ctx.bot.send_message(chat_id,
        f"鉁� *小写械谢泻邪 懈褋锌芯谢薪械薪邪*{mt}\n\n"
        f"{se} *{order['symbol']}*\n"
        f"孝懈锌:    {TRADE_TYPES.get(order.get('type','spot'),'')}\n"
        f"袣芯谢-胁芯: `{order['qty']:.6f}`\n"
        f"笑械薪邪:   `${order['price']:,.4f}`\n"
        f"袠褌芯谐芯:  `${order['total']:.2f}`\n"
        f"ID:     `{order['orderId']}`"
        +(f"\n馃 _{note}_" if note else ""),
        parse_mode=ParseMode.MARKDOWN, reply_markup=back())

async def _auto_job(ctx):
    d=ctx.job.data; uid=d["uid"]
    if not USER_DATA[uid].get("pending_trade"): return
    chat_id=USER_DATA[uid]["chat_id"]
    try:
        await ctx.bot.edit_message_text(chat_id=chat_id, message_id=d["msg_id"],
                                        text=f"鈴� 袗胁褌芯-懈褋锌芯谢薪械薪懈械 {d['side']} ${d['amount']} {d['coin']}...",
                                        parse_mode=ParseMode.MARKDOWN)
    except: pass
    await do_trade(uid, ctx, d["coin"], d["side"], d["amount"],
                   confirmed=True, ttype=d.get("ttype","spot"),
                   note=f"袗胁褌芯 褔械褉械蟹 {AUTO_CONFIRM_TIMEOUT}褋")

async def do_auto_trade(uid, chat_id, coin, ctx):
    if not USER_DATA[uid]["auto_enabled"]: return
    USER_DATA[uid]["chat_id"]=chat_id
    ta=compute_ta(coin); t=get_price(coin); p=t.get("price",0)
    ttype=USER_DATA[uid]["auto_type"]; amount=USER_DATA[uid]["auto_size"]
    if ta["score"]>=2: side="BUY"
    elif ta["score"]<=-2: side="SELL"
    else: return
    se="馃洅" if side=="BUY" else "馃挵"
    rows=[]; row=[]
    for s in TRADE_SIZES:
        row.append(InlineKeyboardButton(f"${s}", callback_data=f"ok_{side.lower()}_{coin.upper()}_{s}_{ttype}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(f"鈴� 袗胁褌芯 ${amount} 褔械褉械蟹 {AUTO_CONFIRM_TIMEOUT}褋", callback_data="noop")])
    rows.append([InlineKeyboardButton("鉂� 袩褉芯锌褍褋褌懈褌褜", callback_data="cancel_trade")])
    sent=await ctx.bot.send_message(chat_id,
        f"馃 *袗胁褌芯-褋懈谐薪邪谢*\n\n"
        f"袦芯薪械褌邪: *{coin.upper()}USDT*\n"
        f"孝懈锌:    {TRADE_TYPES.get(ttype,'')}\n"
        f"笑械薪邪:   `${p:,.4f}`\n"
        f"小懈谐薪邪谢: {ta['signal']}\n"
        f"RSI:    `{ta['rsi']}`\n\n"
        f"{se} 袩褉械写谢芯卸械薪懈械: *{'袣校袩袠孝鞋' if side=='BUY' else '袩袪袨袛袗孝鞋'}*\n"
        f"袙褘斜械褉懈褌械 褋褍屑屑褍 懈谢懈 卸写懈褌械 {AUTO_CONFIRM_TIMEOUT}褋:",
        parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(rows))
    USER_DATA[uid]["pending_trade"]={"coin":coin,"side":side,"amount":amount,
                                      "msg_id":sent.message_id,"timestamp":time.time(),
                                      "chat_id":chat_id,"ttype":ttype}
    ctx.job_queue.run_once(_auto_job, when=AUTO_CONFIRM_TIMEOUT,
                           data={"uid":uid,"coin":coin,"side":side,"amount":amount,
                                 "msg_id":sent.message_id,"ttype":ttype},
                           name=f"auto_{uid}")

# 鈹€鈹€ COMMANDS 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
async def cmd_start(u,c):
    uid=u.effective_user.id; name=u.effective_user.first_name or "孝褉械泄写械褉"
    USER_DATA[uid]["chat_id"]=u.effective_chat.id
    live="\n鈿狅笍 _袛械屑芯-褉械卸懈屑_" if not bc else ("\n馃煛 _Testnet_" if USE_TESTNET else "\n馃煝 _LIVE 褌芯褉谐芯胁谢褟_")
    st="馃煝 袙袣袥" if USER_DATA[uid]["auto_enabled"] else "馃敶 袙蝎袣袥"
    await u.message.reply_text(
        f"馃憢 *袛芯斜褉芯 锌芯卸邪谢芯胁邪褌褜, {name}!*\n\n"
        f"馃 *Binance Pro Trading Bot*\n"
        f"鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣\n"
        f"馃洅 袩芯泻褍锌泻邪 / 馃挵 袩褉芯写邪卸邪 胁褉褍褔薪褍褞\n"
        f"馃搱 小锌芯褌 | 馃敭 肖褜褞褔械褉褋褘 | 馃挸 袦邪褉卸邪\n"
        f"馃 袗胁褌芯-褌褉械泄写: {st}\n"
        f"鈴� 孝邪泄屑邪褍褌: {AUTO_CONFIRM_TIMEOUT}褋 鈫� 邪胁褌芯\n"
        f"馃挼 肖懈泻褋. 褋褍屑屑褘 $5-$50 + 褋胁芯褟 褋褍屑屑邪\n"
        f"馃敂 袗谢械褉褌褘 锌芯 胁褋械屑 15 屑芯薪械褌邪屑\n"
        f"馃搲 袚褉邪褎懈泻懈: 15m/1h/4h/1d/1w\n"
        f"{live}\n\n"
        f"馃憞 *袙褘斜械褉懈褌械 写械泄褋褌胁懈械:*",
        parse_mode=ParseMode.MARKDOWN, reply_markup=main_kb())

async def cmd_help(u,c):
    await u.message.reply_text(
        "馃摎 *袣袨袦袗袧袛蝎*\n\n"
        "`/start` 鈥� 袚谢邪胁薪芯械 屑械薪褞\n"
        "`/buy BTC 20` 鈥� 袣褍锌懈褌褜 $20 BTC\n"
        "`/sell ETH 15` 鈥� 袩褉芯写邪褌褜 $15 ETH\n"
        "`/auto on` 懈谢懈 `off` 鈥� 袙泻谢/胁褘泻谢 邪胁褌芯\n"
        "`/scan` 鈥� 小泻邪薪懈褉芯胁邪褌褜 屑芯薪械褌褘\n"
        "`/price BTC ETH` 鈥� 笑械薪褘\n"
        "`/chart BTC 1h` 鈥� 袚褉邪褎懈泻\n"
        "`/portfolio` 鈥� 袩芯褉褌褎械谢褜\n"
        "`/orders` 鈥� 袠褋褌芯褉懈褟 褋写械谢芯泻\n"
        "`/balance` 鈥� 袘邪谢邪薪褋\n"
        "`/analysis BTC` 鈥� TA 邪薪邪谢懈蟹\n"
        "`/alert BTC above 70000`\n"
        "`/fg` 鈥� 小褌褉邪褏 懈 袞邪写薪芯褋褌褜\n\n"
        f"馃獧 袦芯薪械褌褘: {', '.join(TOP_COINS)}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=back())

async def cmd_buy(u,c):
    args=c.args
    if len(args)<2:
        await u.message.reply_text("馃搶 `/buy BTC 20`", parse_mode=ParseMode.MARKDOWN); return
    uid=u.effective_user.id
    await do_trade(u, c, args[0], "BUY", float(args[1]), ttype=USER_DATA[uid]["auto_type"])

async def cmd_sell(u,c):
    args=c.args
    if len(args)<2:
        await u.message.reply_text("馃搶 `/sell ETH 15`", parse_mode=ParseMode.MARKDOWN); return
    uid=u.effective_user.id
    await do_trade(u, c, args[0], "SELL", float(args[1]), ttype=USER_DATA[uid]["auto_type"])

async def cmd_auto(u,c):
    uid=u.effective_user.id; args=c.args
    if args and args[0].lower() in ("on","off","胁泻谢","胁褘泻谢"):
        on=args[0].lower() in ("on","胁泻谢")
        USER_DATA[uid]["auto_enabled"]=on
        await u.message.reply_text(f"馃 袗胁褌芯-褌褉械泄写: *{'馃煝 袙袣袥挟效衼袧' if on else '馃敶 袙蝎袣袥挟效袝袧'}*",
                                    parse_mode=ParseMode.MARKDOWN)
        return
    await u.message.reply_text("馃 *袗胁褌芯-褌褉械泄写:*", parse_mode=ParseMode.MARKDOWN, reply_markup=auto_kb(uid))

async def cmd_scan(u,c):
    uid=u.effective_user.id
    msg=await u.message.reply_text("馃攳 小泻邪薪懈褉芯胁邪薪懈械 15 屑芯薪械褌...")
    coins=USER_DATA[uid]["auto_coins"] or TOP_COINS
    best_coin=best_ta=None; best=0
    for coin in coins:
        ta=compute_ta(coin)
        if abs(ta["score"])>abs(best): best=ta["score"]; best_coin=coin; best_ta=ta
    if abs(best)>=2:
        await ctx_edit(c, u.effective_chat.id, msg.message_id,
            f"馃弳 袥褍褔褕懈泄 褋懈谐薪邪谢: *{best_coin}USDT*\n"
            f"小懈谐薪邪谢: {best_ta['signal']} | RSI: `{best_ta['rsi']}`\n\n孝芯褉谐芯胁邪褌褜?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("馃 孝芯褉谐芯胁邪褌褜", callback_data=f"auto_do_{best_coin}"),
                 InlineKeyboardButton("鉂� 袩褉芯锌褍褋褌懈褌褜", callback_data="m_main")]
            ]))
    else:
        await ctx_edit(c, u.effective_chat.id, msg.message_id, "鈿� 袧械褌 褋懈谢褜薪褘褏 褋懈谐薪邪谢芯胁.", reply_markup=back())

async def ctx_edit(ctx, chat_id, msg_id, text, reply_markup=None):
    await ctx.bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                     text=text, parse_mode=ParseMode.MARKDOWN,
                                     reply_markup=reply_markup)

async def cmd_price(u,c):
    args=c.args or ["BTC","ETH","SOL"]
    lines=["馃捁 *笑袝袧蝎*\n"]
    for coin in args[:6]:
        t=get_price(coin)
        if "error" in t: lines.append(f"鉂� {coin}: {t['error']}")
        else:
            e="馃煝" if t["change"]>=0 else "馃敶"
            lines.append(f"{e} *{t['symbol']}*: `${t['price']:,.4f}` ({t['change']:+.2f}%)")
    await u.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cmd_chart(u,c):
    args=c.args; coin=args[0] if args else "BTC"; iv=args[1] if len(args)>1 else "1h"
    msg=await u.message.reply_text(f"鈴� 袚褉邪褎懈泻 {coin.upper()} [{iv}]...")
    chart=ascii_chart(coin, iv); t=get_price(coin)
    await ctx_edit(c, u.effective_chat.id, msg.message_id,
        f"馃搲 *{coin.upper()}USDT* [{iv}]\n```\n{chart}\n```",
        reply_markup=chart_kb(coin.upper()))

async def cmd_portfolio(u,c):
    uid=u.effective_user.id
    await u.message.reply_text(portfolio_text(uid), parse_mode=ParseMode.MARKDOWN, reply_markup=back())

async def cmd_orders(u,c):
    uid=u.effective_user.id
    msg=await u.message.reply_text("鈴� 袟邪谐褉褍卸邪褞 懈褋褌芯褉懈褞 褋写械谢芯泻...")
    trades=get_real_trades()
    if trades:
        lines=[f"馃摉 *袠褋褌芯褉懈褟 褋写械谢芯泻 Binance* ({len(trades)})\n"]
        for o in trades[:15]:
            e="馃煝" if o["side"]=="BUY" else "馃敶"
            lines.append(f"{e} `{o['time']}` *{o['symbol']}*\n"
                         f"   {o['side']} `{o['qty']:.6f}` @ `${o['price']:.4f}` = `${o['total']:.2f}`\n")
        await ctx_edit(c, u.effective_chat.id, msg.message_id, "\n".join(lines), reply_markup=back())
        return
    local=USER_DATA[uid]["orders"]
    if not local:
        await ctx_edit(c, u.effective_chat.id, msg.message_id,
            "馃摥 *袧械褌 懈褋褌芯褉懈懈 褋写械谢芯泻*\n\n"
            "袧邪 Binance 薪械褌 褋写械谢芯泻 锌芯 胁褘斜褉邪薪薪褘屑 屑芯薪械褌邪屑.\n\n"
            "袙芯蟹屑芯卸薪褘械 锌褉懈褔懈薪褘:\n"
            "鈥� 袝褖褢 薪械 褌芯褉谐芯胁邪谢懈 褝褌懈屑懈 屑芯薪械褌邪屑懈\n"
            "鈥� API 薪械 懈屑械械褌 褉邪蟹褉械褕械薪懈褟 Read\n"
            "鈥� 小写械谢泻邪屑 斜芯谢械械 3 屑械褋褟褑械胁\n\n"
            "小芯胁械褉褕懈褌械 锌械褉胁褍褞 褋写械谢泻褍 褔械褉械蟹 斜芯褌邪!",
            reply_markup=back())
        return
    lines=["馃摉 *袠褋褌芯褉懈褟 褋写械谢芯泻 (斜芯褌)*\n"]
    for o in local[:10]:
        e="馃煝" if o["side"]=="BUY" else "馃敶"
        lines.append(f"{e} `{o['time']}` *{o['symbol']}*\n"
                     f"   {o['side']} `{o['qty']:.6f}` @ `${o['price']:.4f}` = `${o['total']:.2f}`\n")
    await ctx_edit(c, u.effective_chat.id, msg.message_id, "\n".join(lines), reply_markup=back())

async def cmd_balance(u,c):
    bals=get_real_balance()
    if "error" in bals:
        await u.message.reply_text(f"鉂� {bals['error']}"); return
    is_mock=bals.pop("mock",False)
    mt=" _(袛械屑芯)_" if is_mock else (" _(Testnet)_" if USE_TESTNET else "")
    lines=[f"馃挸 *袘邪谢邪薪褋 Binance*{mt}\n"]
    total=0.0; usdt=bals.pop("USDT",0)
    if usdt>0: lines.append(f"馃挼 *USDT*: `${usdt:.4f}`"); total+=usdt
    for asset,qty in sorted(bals.items(),key=lambda x:-x[1]):
        t=get_price(asset)
        if "error" not in t:
            v=qty*t["price"]; total+=v
            lines.append(f"  鈥� *{asset}*: `{qty:.6f}` 鈮� `${v:.2f}`")
        else:
            lines.append(f"  鈥� *{asset}*: `{qty:.6f}`")
    lines.append(f"\n馃拵 *袠褌芯谐芯 鈮�* `${total:.2f} USDT`")
    if usdt<5: lines.append(f"\n鈿狅笍 USDT 屑械薪褜褕械 $5 鈥� 锌芯锌芯谢薪懈褌械 写谢褟 褌芯褉谐芯胁谢懈")
    else: lines.append(f"\n鉁� 袛芯褋褌褍锌薪芯 写谢褟 褌芯褉谐芯胁谢懈: `${usdt:.2f}`")
    await u.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back())

async def cmd_analysis(u,c):
    args=c.args; coin=args[0] if args else "BTC"; iv=args[1] if len(args)>1 else "1h"
    await u.message.reply_text(f"鈴� 袗薪邪谢懈蟹 *{coin.upper()}* [{iv}]...", parse_mode=ParseMode.MARKDOWN)
    ta=compute_ta(coin,iv); t=get_price(coin)
    await u.message.reply_text(ta_text(coin.upper(),t.get("price",0),ta,iv), parse_mode=ParseMode.MARKDOWN)

async def cmd_alert(u,c):
    uid=u.effective_user.id; args=c.args
    if len(args)<3:
        await u.message.reply_text("馃搶 `/alert BTC above 70000`\n馃搶 `/alert ETH below 3000`",
                                    parse_mode=ParseMode.MARKDOWN); return
    s,cond,price=args[0].upper(),args[1].lower(),float(args[2])
    USER_DATA[uid]["alerts"].append({"symbol":sym(s),"condition":cond,"price":price,
                                     "chat_id":u.effective_chat.id})
    await u.message.reply_text(
        f"馃敂 袗谢械褉褌 褍褋褌邪薪芯胁谢械薪!\n*{sym(s)}* {'猬嗭笍' if cond=='above' else '猬囷笍'} `${price:,.2f}`",
        parse_mode=ParseMode.MARKDOWN)

async def cmd_fg(u,c):
    fg=fear_greed(); bar="鈻�"*int(fg["value"]/5)+"鈻�"*(20-int(fg["value"]/5))
    await u.message.reply_text(
        f"馃槺 *小褌褉邪褏 懈 袞邪写薪芯褋褌褜*\n```\n[{bar}]\n```\n{fg['emoji']} *{fg['value']}/100* 鈥� {fg['label']}",
        parse_mode=ParseMode.MARKDOWN)

# 鈹€鈹€ TEXT INPUT HANDLER 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
async def text_handler(u, c):
    uid=u.effective_user.id; text=u.message.text.strip()
    w=USER_DATA[uid].get("waiting_input")
    if not w: return

    # Alert price input
    if w.get("type")=="alert_price":
        try:
            price=float(text.replace("$","").replace(",","."))
            coin=w["coin"]; cond=w["cond"]
            USER_DATA[uid]["alerts"].append({"symbol":sym(coin),"condition":cond,
                                              "price":price,"chat_id":u.effective_chat.id})
            USER_DATA[uid]["waiting_input"]=None
            e="猬嗭笍" if cond=="above" else "猬囷笍"
            await u.message.reply_text(
                f"鉁� 袗谢械褉褌 褍褋褌邪薪芯胁谢械薪!\n*{sym(coin)}* {e} `${price:,.2f}`",
                parse_mode=ParseMode.MARKDOWN, reply_markup=back("m_alerts"))
        except:
            await u.message.reply_text("鉂� 袙胁械写懈褌械 褌芯谢褜泻芯 褔懈褋谢芯: `70000`", parse_mode=ParseMode.MARKDOWN)
        return

    # Custom trade amount
    if w.get("type") in ("buy_amount","sell_amount","auto_size"):
        try:
            amount=float(text.replace("$","").replace(",","."))
            if amount<=0: raise ValueError
        except:
            await u.message.reply_text("鉂� 袙胁械写懈褌械 褔懈褋谢芯: `25.5`", parse_mode=ParseMode.MARKDOWN); return
        USER_DATA[uid]["waiting_input"]=None
        if w["type"]=="auto_size":
            USER_DATA[uid]["auto_size"]=amount
            await u.message.reply_text(f"鉁� 小褍屑屑邪 邪胁褌芯: `${amount}`", parse_mode=ParseMode.MARKDOWN,
                                        reply_markup=auto_kb(uid))
        else:
            side="BUY" if w["type"]=="buy_amount" else "SELL"
            await do_trade(u, c, w["coin"], side, amount, ttype=w.get("ttype",USER_DATA[uid]["auto_type"]))

# 鈹€鈹€ CALLBACK HANDLER 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
async def cb(u, c):
    q=u.callback_query; await q.answer(); d=q.data
    uid=u.effective_user.id; USER_DATA[uid]["chat_id"]=u.effective_chat.id

    # MAIN
    if d=="m_main":
        await q.edit_message_text("馃 *Binance Pro Bot*\n\n馃憞 袙褘斜械褉懈褌械 写械泄褋褌胁懈械:",
                                   parse_mode=ParseMode.MARKDOWN, reply_markup=main_kb())
    elif d=="m_buy":
        await q.edit_message_text("馃洅 *袣校袩袠孝鞋 鈥� 袙褘斜械褉懈褌械 屑芯薪械褌褍:*",
                                   parse_mode=ParseMode.MARKDOWN, reply_markup=coins_kb("buyc","m_main"))
    elif d=="m_sell":
        await q.edit_message_text("馃挵 *袩袪袨袛袗孝鞋 鈥� 袙褘斜械褉懈褌械 屑芯薪械褌褍:*",
                                   parse_mode=ParseMode.MARKDOWN, reply_markup=coins_kb("sellc","m_main"))
    elif d=="m_portfolio":
        await q.edit_message_text(portfolio_text(uid), parse_mode=ParseMode.MARKDOWN, reply_markup=back())
    elif d=="m_balance":
        bals=get_real_balance(); is_mock=bals.pop("mock",False)
        mt=" _(袛械屑芯)_" if is_mock else ""
        lines=[f"馃挸 *袘邪谢邪薪褋*{mt}\n"]; total=0.0; usdt=bals.pop("USDT",0)
        if usdt>0: lines.append(f"馃挼 *USDT*: `${usdt:.4f}`"); total+=usdt
        for asset,qty in sorted(bals.items(),key=lambda x:-x[1])[:12]:
            t=get_price(asset)
            if "error" not in t: v=qty*t["price"]; total+=v; lines.append(f"鈥� *{asset}*: `{qty:.6f}` 鈮� `${v:.2f}`")
            else: lines.append(f"鈥� *{asset}*: `{qty:.6f}`")
        lines.append(f"\n馃拵 *袠褌芯谐芯:* `${total:.2f}`")
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back())

    elif d=="m_orders":
        await q.edit_message_text("鈴� 袟邪谐褉褍卸邪褞...", parse_mode=ParseMode.MARKDOWN)
        trades=get_real_trades()
        if trades:
            lines=[f"馃摉 *小写械谢泻懈 Binance* ({len(trades)})\n"]
            for o in trades[:10]:
                e="馃煝" if o["side"]=="BUY" else "馃敶"
                lines.append(f"{e} *{o['symbol']}* {o['side']} `${o['total']:.2f}` 鈥� _{o['time']}_")
            await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back())
        else:
            local=USER_DATA[uid]["orders"]
            if not local:
                await q.edit_message_text(
                    "馃摥 *袧械褌 懈褋褌芯褉懈懈 褋写械谢芯泻*\n\n袧邪 Binance 薪械褌 褋写械谢芯泻 锌芯 褝褌懈屑 屑芯薪械褌邪屑.\n小芯胁械褉褕懈褌械 锌械褉胁褍褞 褋写械谢泻褍!",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=back())
            else:
                lines=["馃摉 *小写械谢泻懈 (斜芯褌)*\n"]
                for o in local[:8]:
                    e="馃煝" if o["side"]=="BUY" else "馃敶"
                    lines.append(f"{e} *{o['symbol']}* `${o['total']:.2f}` 鈥� _{o['time']}_")
                await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back())

    elif d=="m_prices":
        lines=["馃捁 *孝袨袩 15 笑袝袧*\n"]
        for coin in TOP_COINS:
            t=get_price(coin)
            if "error" not in t:
                e="馃煝" if t["change"]>=0 else "馃敶"
                lines.append(f"{e} *{coin}*: `${t['price']:,.4f}` `{t['change']:+.2f}%`")
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back())

    elif d=="m_screener":
        res=[]
        for coin in TOP_COINS:
            t=get_price(coin)
            if "error" not in t: res.append((coin,t["change"],t["price"]))
        res.sort(key=lambda x:x[1],reverse=True)
        lines=["馃搵 *小袣袪袠袧袝袪*\n","馃煝 *袪芯褋褌:*"]
        for coin,chg,pr in res[:5]: lines.append(f"  鈥� *{coin}*: `{chg:+.2f}%` @ `${pr:,.4f}`")
        lines.append("\n馃敶 *袩邪写械薪懈械:*")
        for coin,chg,pr in res[-5:]: lines.append(f"  鈥� *{coin}*: `{chg:+.2f}%` @ `${pr:,.4f}`")
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back())

    elif d=="m_fg":
        fg=fear_greed(); bar="鈻�"*int(fg["value"]/5)+"鈻�"*(20-int(fg["value"]/5))
        await q.edit_message_text(
            f"馃槺 *小褌褉邪褏 懈 袞邪写薪芯褋褌褜*\n```\n[{bar}]\n```\n{fg['emoji']} *{fg['value']}/100* 鈥� {fg['label']}",
            parse_mode=ParseMode.MARKDOWN, reply_markup=back())

    elif d=="m_whale":
        lines=["馃悑 *袣褉褍锌薪褘械 褋写械谢泻懈*\n"]
        for _ in range(6):
            coin=random.choice(TOP_COINS); amt=round(random.uniform(50,3000),1)
            tp=get_price(coin)["price"]; usd=int(amt*tp)
            side=random.choice(["馃悑 袩袨袣校袩袣袗","馃 袩袪袨袛袗袞袗"]); ago=random.randint(1,59)
            lines.append(f"{side} `{amt} {coin}` ~`${usd:,}` 鈥� `{ago}屑懈薪 薪邪蟹邪写`")
        await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=back())

    elif d=="m_help":
        await q.edit_message_text("馃搶 袠褋锌芯谢褜蟹褍泄褌械 `/help`", parse_mode=ParseMode.MARKDOWN, reply_markup=back())

    # CHART
    elif d=="m_chart":
        await q.edit_message_text("馃搲 *袚褉邪褎懈泻 鈥� 袙褘斜械褉懈褌械 屑芯薪械褌褍:*",
                                   parse_mode=ParseMode.MARKDOWN, reply_markup=coins_kb("chartc","m_main"))
    elif d.startswith("chartc_"):
        coin=d.split("_")[1]
        await q.edit_message_text(f"馃搲 *{coin}USDT* 鈥� 懈薪褌械褉胁邪谢:",
                                   parse_mode=ParseMode.MARKDOWN, reply_markup=chart_kb(coin))
    elif d.startswith("chart_") and len(d.split("_"))==3:
        _,coin,iv=d.split("_"); chart=ascii_chart(coin,iv)
        await q.edit_message_text(f"馃搲 *{coin}USDT* [{iv}]\n```\n{chart}\n```",
                                   parse_mode=ParseMode.MARKDOWN, reply_markup=chart_kb(coin))

    # ANALYSIS
    elif d=="m_analysis":
        await q.edit_message_text("馃敩 *袗薪邪谢懈蟹 鈥� 袙褘斜械褉懈褌械 屑芯薪械褌褍:*",
                                   parse_mode=ParseMode.MARKDOWN, reply_markup=coins_kb("tac","m_main"))
    elif d.startswith("tac_"):
        coin=d.split("_")[1]; ta=compute_ta(coin); t=get_price(coin)
        await q.edit_message_text(ta_text(coin.upper(),t.get("price",0),ta,"1h"),
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([
                                       [InlineKeyboardButton("馃洅 袣校袩袠孝鞋",callback_data=f"buyc_{coin}"),
                                        InlineKeyboardButton("馃挵 袩袪袨袛袗孝鞋",callback_data=f"sellc_{coin}"),
                                        InlineKeyboardButton("馃敊",callback_data="m_analysis")]]))

    # BUY/SELL COIN
    elif d.startswith("buyc_"):
        coin=d.split("_")[1]; t=get_price(coin)
        await q.edit_message_text(f"馃洅 *袣校袩袠孝鞋 {coin}USDT*\n笑械薪邪: `${t.get('price',0):,.4f}`\n\n袙褘斜械褉懈褌械 褋褍屑屑褍:",
                                   parse_mode=ParseMode.MARKDOWN, reply_markup=sizes_kb("buy",coin,"m_buy"))
    elif d.startswith("sellc_"):
        coin=d.split("_")[1]; t=get_price(coin)
        await q.edit_message_text(f"馃挵 *袩袪袨袛袗孝鞋 {coin}USDT*\n笑械薪邪: `${t.get('price',0):,.4f}`\n\n袙褘斜械褉懈褌械 褋褍屑屑褍:",
                                   parse_mode=ParseMode.MARKDOWN, reply_markup=sizes_kb("sell",coin,"m_sell"))
    elif d.startswith("buy_") and not d.startswith("buyc_"):
        parts=d.split("_"); coin=parts[1]; amount=float(parts[2])
        ttype=USER_DATA[uid]["auto_type"]
        await do_trade(u, c, coin, "BUY", amount, ttype=ttype)
    elif d.startswith("sell_") and not d.startswith("sellc_"):
        parts=d.split("_"); coin=parts[1]; amount=float(parts[2])
        ttype=USER_DATA[uid]["auto_type"]
        await do_trade(u, c, coin, "SELL", amount, ttype=ttype)

    # CUSTOM AMOUNT
    elif d.startswith("custom_buy_"):
        coin=d.split("_")[2]
        USER_DATA[uid]["waiting_input"]={"type":"buy_amount","coin":coin,"ttype":USER_DATA[uid]["auto_type"]}
        t=get_price(coin)
        await q.edit_message_text(f"鉁忥笍 *小胁芯褟 褋褍屑屑邪 写谢褟 锌芯泻褍锌泻懈 {coin}USDT*\n笑械薪邪: `${t.get('price',0):,.4f}`\n\n袙胁械写懈褌械 褋褍屑屑褍 胁 $:",
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("鉂� 袨褌屑械薪邪",callback_data="m_main")]]))
    elif d.startswith("custom_sell_"):
        coin=d.split("_")[2]
        USER_DATA[uid]["waiting_input"]={"type":"sell_amount","coin":coin,"ttype":USER_DATA[uid]["auto_type"]}
        t=get_price(coin)
        await q.edit_message_text(f"鉁忥笍 *小胁芯褟 褋褍屑屑邪 写谢褟 锌褉芯写邪卸懈 {coin}USDT*\n笑械薪邪: `${t.get('price',0):,.4f}`\n\n袙胁械写懈褌械 褋褍屑屑褍 胁 $:",
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("鉂� 袨褌屑械薪邪",callback_data="m_main")]]))

    # CONFIRM TRADE
    elif d.startswith("ok_"):
        parts=d.split("_"); side=parts[1].upper(); coin=parts[2]
        amount=float(parts[3]); ttype=parts[4] if len(parts)>4 else "spot"
        for j in c.job_queue.get_jobs_by_name(f"auto_{uid}"): j.schedule_removal()
        USER_DATA[uid]["pending_trade"]=None
        await do_trade(u, c, coin, side, amount, confirmed=True, ttype=ttype, note="袩芯谢褜蟹芯胁邪褌械谢褜 锌芯写褌胁械褉写懈谢")

    elif d=="cancel_trade":
        for j in c.job_queue.get_jobs_by_name(f"auto_{uid}"): j.schedule_removal()
        USER_DATA[uid]["pending_trade"]=None
        await q.edit_message_text("鉂� 小写械谢泻邪 芯褌屑械薪械薪邪.", reply_markup=back())

    # AUTO TRADE
    elif d=="m_auto":
        st="馃煝 袙袣袥" if USER_DATA[uid]["auto_enabled"] else "馃敶 袙蝎袣袥"
        tt=TRADE_TYPES.get(USER_DATA[uid]["auto_type"],""); sz=USER_DATA[uid]["auto_size"]
        nc=len(USER_DATA[uid]["auto_coins"])
        await q.edit_message_text(
            f"馃 *袗胁褌芯-孝褉械泄写*\n\n小褌邪褌褍褋: *{st}*\n孝懈锌: {tt}\n小褍屑屑邪: `${sz}`\n袦芯薪械褌: `{nc}/15`\n\n"
            f"_袗谢谐芯褉懈褌屑: RSI + MACD + Bollinger Bands_",
            parse_mode=ParseMode.MARKDOWN, reply_markup=auto_kb(uid))
    elif d=="auto_toggle":
        USER_DATA[uid]["auto_enabled"]=not USER_DATA[uid]["auto_enabled"]
        st="馃煝 袙袣袥" if USER_DATA[uid]["auto_enabled"] else "馃敶 袙蝎袣袥"
        await q.edit_message_text(f"馃 *袗胁褌芯-褌褉械泄写: {st}*", parse_mode=ParseMode.MARKDOWN, reply_markup=auto_kb(uid))
    elif d=="auto_type":
        await q.edit_message_text("馃敡 *孝懈锌 褌芯褉谐芯胁谢懈:*", parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([
                                       [InlineKeyboardButton("馃搱 小锌芯褌",     callback_data="set_type_spot")],
                                       [InlineKeyboardButton("馃敭 肖褜褞褔械褉褋褘",callback_data="set_type_futures")],
                                       [InlineKeyboardButton("馃挸 袦邪褉卸邪",   callback_data="set_type_margin")],
                                       [InlineKeyboardButton("馃敊 袧邪蟹邪写",   callback_data="m_auto")]]))
    elif d.startswith("set_type_"):
        USER_DATA[uid]["auto_type"]=d.split("_")[2]
        await q.edit_message_text(f"鉁� 孝懈锌: *{TRADE_TYPES[USER_DATA[uid]['auto_type']]}*",
                                   parse_mode=ParseMode.MARKDOWN, reply_markup=auto_kb(uid))
    elif d=="auto_size":
        rows=[]; row=[]
        for s in TRADE_SIZES:
            row.append(InlineKeyboardButton(f"${s}", callback_data=f"set_size_{s}"))
            if len(row)==5: rows.append(row); row=[]
        if row: rows.append(row)
        rows.append([InlineKeyboardButton("鉁忥笍 小胁芯褟 褋褍屑屑邪", callback_data="set_size_custom")])
        rows.append([InlineKeyboardButton("馃敊 袧邪蟹邪写", callback_data="m_auto")])
        await q.edit_message_text("馃挼 *小褍屑屑邪 邪胁褌芯-褌褉械泄写邪:*", parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup(rows))
    elif d.startswith("set_size_"):
        val=d.split("_")[2]
        if val=="custom":
            USER_DATA[uid]["waiting_input"]={"type":"auto_size","coin":"","ttype":""}
            await q.edit_message_text("鉁忥笍 袙胁械写懈褌械 褋褍屑屑褍 胁 $:\n袩褉懈屑械褉: `35`", parse_mode=ParseMode.MARKDOWN,
                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("鉂� 袨褌屑械薪邪",callback_data="m_auto")]]))
        else:
            USER_DATA[uid]["auto_size"]=float(val)
            await q.edit_message_text(f"鉁� 小褍屑屑邪 邪胁褌芯: `${val}`", parse_mode=ParseMode.MARKDOWN, reply_markup=auto_kb(uid))
    elif d=="auto_coins":
        await q.edit_message_text("馃獧 *袦芯薪械褌褘 写谢褟 邪胁褌芯-褌褉械泄写邪:*", parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=auto_coins_kb(uid))
    elif d.startswith("acoin_"):
        val=d.split("_")[1]
        if val=="all": USER_DATA[uid]["auto_coins"]=list(TOP_COINS)
        elif val=="none": USER_DATA[uid]["auto_coins"]=[]
        else:
            coins=USER_DATA[uid]["auto_coins"]
            if val in coins: coins.remove(val)
            else: coins.append(val)
        await q.edit_message_text("馃獧 *袦芯薪械褌褘:*", parse_mode=ParseMode.MARKDOWN, reply_markup=auto_coins_kb(uid))
    elif d=="auto_scan":
        await q.edit_message_text("馃攳 小泻邪薪懈褉芯胁邪薪懈械...")
        coins=USER_DATA[uid]["auto_coins"] or TOP_COINS
        best_coin=best_ta=None; best=0
        for coin in coins:
            ta=compute_ta(coin)
            if abs(ta["score"])>abs(best): best=ta["score"]; best_coin=coin; best_ta=ta
        if abs(best)>=2:
            await q.edit_message_text(
                f"馃弳 *{best_coin}USDT* 鈥� {best_ta['signal']}\nRSI: `{best_ta['rsi']}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("馃 孝芯褉谐芯胁邪褌褜", callback_data=f"auto_do_{best_coin}"),
                     InlineKeyboardButton("鉂� 袩褉芯锌褍褋褌懈褌褜",callback_data="m_auto")]]))
        else:
            await q.edit_message_text("鈿� 袧械褌 褋懈谢褜薪褘褏 褋懈谐薪邪谢芯胁.", reply_markup=back("m_auto"))
    elif d.startswith("auto_do_"):
        coin=d.split("_")[2]
        await do_auto_trade(uid, u.effective_chat.id, coin, c)

    # ALERTS
    elif d=="m_alerts":
        alerts=USER_DATA[uid]["alerts"]
        if not alerts: txt="馃敃 *袗谢械褉褌褘*\n\n袧械褌 邪泻褌懈胁薪褘褏 邪谢械褉褌芯胁."
        else:
            lines=["馃敂 *袗泻褌懈胁薪褘械 邪谢械褉褌褘:*\n"]
            for i,a in enumerate(alerts,1):
                e="猬嗭笍" if a["condition"]=="above" else "猬囷笍"
                lines.append(f"`{i}.` *{a['symbol']}* {e} `${a['price']:,.2f}`")
            txt="\n".join(lines)
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([
                                       [InlineKeyboardButton("鉃� 袛芯斜邪胁懈褌褜", callback_data="alert_add")],
                                       [InlineKeyboardButton("馃棏 校写邪谢懈褌褜 胁褋械", callback_data="alert_clear")],
                                       [InlineKeyboardButton("馃敊 袧邪蟹邪写", callback_data="m_main")]]))
    elif d=="alert_add":
        await q.edit_message_text("馃敂 *袙褘斜械褉懈褌械 屑芯薪械褌褍 写谢褟 邪谢械褉褌邪:*",
                                   parse_mode=ParseMode.MARKDOWN, reply_markup=coins_kb("alertc","m_alerts"))
    elif d.startswith("alertc_"):
        coin=d.split("_")[1]; t=get_price(coin)
        await q.edit_message_text(
            f"馃敂 *{coin}USDT*\n孝械泻褍褖邪褟 褑械薪邪: `${t.get('price',0):,.4f}`\n\n袙褘斜械褉懈褌械 褍褋谢芯胁懈械:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("猬嗭笍 袙褘褕械 (above)", callback_data=f"alertcond_{coin}_above"),
                 InlineKeyboardButton("猬囷笍 袧懈卸械 (below)", callback_data=f"alertcond_{coin}_below")],
                [InlineKeyboardButton("馃敊 袧邪蟹邪写", callback_data="alert_add")]]))
    elif d.startswith("alertcond_"):
        parts=d.split("_"); coin=parts[1]; cond=parts[2]
        USER_DATA[uid]["waiting_input"]={"type":"alert_price","coin":coin,"cond":cond}
        t=get_price(coin)
        cond_txt="胁褘褕械 猬嗭笍" if cond=="above" else "薪懈卸械 猬囷笍"
        await q.edit_message_text(
            f"馃敂 *{coin}USDT 鈥� 褑械薪邪 {cond_txt}*\n孝械泻褍褖邪褟: `${t.get('price',0):,.4f}`\n\n鉁忥笍 袙胁械写懈褌械 褑械谢械胁褍褞 褑械薪褍:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("鉂� 袨褌屑械薪邪",callback_data="m_alerts")]]))
    elif d=="alert_clear":
        USER_DATA[uid]["alerts"]=[]
        await q.edit_message_text("馃棏 袙褋械 邪谢械褉褌褘 褍写邪谢械薪褘.", reply_markup=back("m_main"))

    elif d=="noop": pass

# 鈹€鈹€ BACKGROUND JOBS 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
async def alerts_job(ctx):
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
            e="猬嗭笍" if alert["condition"]=="above" else "猬囷笍"
            try:
                await ctx.bot.send_message(alert["chat_id"],
                    f"馃敂 *袗袥袝袪孝!* *{alert['symbol']}* {e} `${alert['price']:,.2f}`\n"
                    f"孝械泻褍褖邪褟: `${cur:,.4f}`", parse_mode=ParseMode.MARKDOWN)
            except Exception as err: log.error(f"Alert: {err}")

async def auto_job(ctx):
    for uid,data in list(USER_DATA.items()):
        if not data.get("auto_enabled"): continue
        if not data.get("chat_id"):      continue
        if data.get("pending_trade"):    continue
        coins=data["auto_coins"] or TOP_COINS
        coin=random.choice(coins); ta=compute_ta(coin)
        if abs(ta["score"])>=2:
            await do_auto_trade(uid, data["chat_id"], coin, ctx)
            await asyncio.sleep(1)

# 鈹€鈹€ HEALTH SERVER 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self,*a): pass

def health():
    HTTPServer(("0.0.0.0",PORT),H).serve_forever()

# 鈹€鈹€ MAIN 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
async def main():
    if TELEGRAM_TOKEN=="YOUR_TOKEN":
        print("Set TELEGRAM_TOKEN!"); return
    Thread(target=health, daemon=True).start()
    app=Application.builder().token(TELEGRAM_TOKEN).build()
    for cmd,fn in [("start",cmd_start),("help",cmd_help),("buy",cmd_buy),("sell",cmd_sell),
                   ("auto",cmd_auto),("scan",cmd_scan),("price",cmd_price),("chart",cmd_chart),
                   ("portfolio",cmd_portfolio),("orders",cmd_orders),("balance",cmd_balance),
                   ("analysis",cmd_analysis),("alert",cmd_alert),("fg",cmd_fg)]:
        app.add_handler(CommandHandler(cmd,fn))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.job_queue.run_repeating(alerts_job, interval=60,  first=15)
    app.job_queue.run_repeating(auto_job,   interval=300, first=60)
    log.info("馃殌 Bot v4.0 started!")
    async with app:
        await app.initialize(); await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__=="__main__":
    asyncio.run(main())
