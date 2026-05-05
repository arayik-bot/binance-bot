"""
BINANCE PRO TRADING BOT v8.0
✅ Auto SL/TP execution
✅ Trailing Stop
✅ Daily PnL report
✅ % Change alerts
✅ Risk management
✅ Crypto news (Russian)
✅ Converter
✅ Smart balance-aware auto trading
✅ Better signals (RSI+MACD+BB+EMA+Volume)
"""
import os, asyncio, logging, time, math, random
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                           ContextTypes, MessageHandler, filters)
from telegram.constants import ParseMode

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
    BINANCE_OK = True
except ImportError:
    BINANCE_OK = False

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
CHART_URL            = "https://arayik-bot.github.io/binance-bot/chart.html"
DAILY_REPORT_HOUR    = 20  # UTC hour for daily report

TRADE_SIZES = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
TOP_COINS   = ["BTC","ETH","BNB","SOL","XRP","ADA","DOGE","AVAX",
               "DOT","MATIC","LINK","LTC","UNI","ATOM","NEAR"]
TRADE_TYPES = {"spot":"📈 Спот","futures":"🔮 Фьючерсы","margin":"💳 Маржа"}

# ── PRICE CACHE ───────────────────────────────────────────────────
_price_cache   = {}
_price_cache_ttl = 30
_balance_cache = {}
_balance_cache_ts = 0
_balance_cache_ttl = 60

# ── STATE ─────────────────────────────────────────────────────────
def default_user():
    return {
        "portfolio":      {},
        "alerts":         [],
        "orders":         [],
        "limit_orders":   [],
        "dca_bots":       [],
        "grid_bots":      [],
        "trailing_stops": {},   # {symbol: {trail_pct, high_price, active}}
        "pending_trade":  None,
        "chat_id":        None,
        "auto_enabled":   False,
        "auto_coins":     list(TOP_COINS),
        "auto_type":      "spot",
        "auto_size":      10,
        "risk_max_trade": 50,   # max $ per trade
        "risk_max_loss":  20,   # max % total loss before stop
        "daily_report":   True,
        "waiting_input":  None,
        "joined":         datetime.now().strftime("%d.%m.%Y"),
        "total_profit":   0.0,
        "scan_idx":       0,    # for rotating coin scan
    }

USER_DATA = defaultdict(default_user)

# ── BINANCE CLIENT ────────────────────────────────────────────────
bc = None
if BINANCE_OK and BINANCE_API_KEY:
    try:
        bc = Client(BINANCE_API_KEY, BINANCE_SECRET, testnet=USE_TESTNET)
        log.info("✅ Binance " + ("TESTNET" if USE_TESTNET else "LIVE"))
    except Exception as e:
        log.warning(f"Binance: {e}")

MOCK = {"BTCUSDT":77500,"ETHUSDT":3450,"BNBUSDT":582,"SOLUSDT":176,
        "XRPUSDT":0.58,"ADAUSDT":0.48,"DOGEUSDT":0.162,"AVAXUSDT":38.7,
        "DOTUSDT":7.8,"MATICUSDT":0.91,"LINKUSDT":18.4,"LTCUSDT":82.0,
        "UNIUSDT":9.3,"ATOMUSDT":10.5,"NEARUSDT":7.1}

def sym(coin):
    c = coin.upper().strip()
    return c if c.endswith("USDT") else c + "USDT"

# ── LOT SIZE ──────────────────────────────────────────────────────
_lot_cache = {}
def get_lot_size(symbol):
    if symbol in _lot_cache: return _lot_cache[symbol]
    if bc:
        try:
            info=bc.get_symbol_info(symbol)
            for f in info["filters"]:
                if f["filterType"]=="LOT_SIZE":
                    step=float(f["stepSize"]); minq=float(f["minQty"])
                    _lot_cache[symbol]=(step,minq); return step,minq
        except: pass
    return 0.00001,0.00001

def round_qty(qty,step):
    if step<=0: return qty
    p=max(0,round(-math.log10(step))); f=10**p
    return math.floor(qty*f)/f

def get_min_notional(symbol):
    if bc:
        try:
            info=bc.get_symbol_info(symbol)
            for f in info["filters"]:
                if f["filterType"] in ("MIN_NOTIONAL","NOTIONAL"):
                    return float(f.get("minNotional",f.get("notional",5)))
        except: pass
    return 5.0

# ── PRICE (with cache) ────────────────────────────────────────────
def get_price(coin):
    s=sym(coin); now=time.time()
    if s in _price_cache:
        cached,ts=_price_cache[s]
        if now-ts<_price_cache_ttl: return cached
    if bc:
        try:
            t=bc.get_ticker(symbol=s)
            result={"symbol":s,"price":float(t["lastPrice"]),
                    "change":float(t["priceChangePercent"]),
                    "high":float(t["highPrice"]),"low":float(t["lowPrice"]),
                    "volume":float(t["volume"])}
            _price_cache[s]=(result,now); return result
        except Exception as e:
            if "1003" in str(e) or "banned" in str(e).lower():
                log.warning("Rate limited — using cache")
                if s in _price_cache: return _price_cache[s][0]
            return {"error":str(e),"symbol":s}
    base=MOCK.get(s,10.0)*random.uniform(0.98,1.02)
    result={"symbol":s,"price":round(base,6),"change":round(random.uniform(-6,6),2),
            "high":round(base*1.04,6),"low":round(base*0.96,6),
            "volume":round(random.uniform(5000,500000),2)}
    _price_cache[s]=(result,now); return result

def get_all_prices():
    """Get all TOP_COINS prices in ONE request to save rate limits."""
    if bc:
        try:
            tickers=bc.get_ticker()
            result={}
            for t in tickers:
                if t["symbol"] in [sym(c) for c in TOP_COINS]:
                    s=t["symbol"]
                    result[s]={"symbol":s,"price":float(t["lastPrice"]),
                               "change":float(t["priceChangePercent"]),
                               "high":float(t["highPrice"]),"low":float(t["lowPrice"]),
                               "volume":float(t["volume"])}
            now=time.time()
            for s,v in result.items():
                _price_cache[s]=(v,now)
            return result
        except: pass
    return {sym(c):get_price(c) for c in TOP_COINS}

def get_klines(coin,interval="1h",limit=120):
    s=sym(coin)
    if bc:
        try: return bc.get_klines(symbol=s,interval=interval,limit=limit)
        except: pass
    base=MOCK.get(s,50.0); data=[]; t=int(time.time()*1000)-limit*3600000
    for _ in range(limit):
        o=base*random.uniform(0.99,1.01); h=o*random.uniform(1.00,1.02)
        lo=o*random.uniform(0.98,1.00); c=random.uniform(lo,h); base=c
        data.append([t,str(o),str(h),str(lo),str(c),str(random.uniform(100,5000)),t+3600000])
        t+=3600000
    return data

def get_real_balance():
    global _balance_cache,_balance_cache_ts
    now=time.time()
    if _balance_cache and now-_balance_cache_ts<_balance_cache_ttl:
        return dict(_balance_cache)
    if bc:
        try:
            acc=bc.get_account()
            result={b["asset"]:float(b["free"])+float(b["locked"])
                    for b in acc["balances"]
                    if float(b["free"])+float(b["locked"])>0.000001}
            _balance_cache=result; _balance_cache_ts=now
            return dict(result)
        except Exception as e:
            if _balance_cache: return dict(_balance_cache)
            return {"_error":str(e)}
    return {"USDT":1000.0,"BTC":0.01,"ETH":0.5,"_mock":True}

def get_real_trades():
    if not bc: return []
    all_trades=[]
    for coin in TOP_COINS:
        s=sym(coin)
        try:
            trades=bc.get_my_trades(symbol=s,limit=5)
            for t in trades:
                all_trades.append({
                    "time":datetime.fromtimestamp(t["time"]/1000).strftime("%d.%m %H:%M"),
                    "symbol":s,"side":"BUY" if t["isBuyer"] else "SELL",
                    "qty":float(t["qty"]),"price":float(t["price"]),
                    "total":float(t["qty"])*float(t["price"]),"ts":t["time"]})
        except: continue
    all_trades.sort(key=lambda x:x["ts"],reverse=True)
    return all_trades

def place_order(coin,side,usdt_amount,trade_type="spot"):
    s=sym(coin); ticker=get_price(coin)
    if "error" in ticker: return {"ok":False,"error":ticker["error"]}
    price=ticker["price"]
    min_n=get_min_notional(s)
    if usdt_amount<min_n: return {"ok":False,"error":f"Минимум: ${min_n}"}
    raw_qty=usdt_amount/price; step,min_qty=get_lot_size(s)
    qty=round_qty(raw_qty,step)
    if qty<min_qty: return {"ok":False,"error":f"Кол-во {qty:.8f} < мин {min_qty}"}
    if bc:
        try:
            if trade_type=="futures":
                order=bc.futures_create_order(symbol=s,side=side,type="MARKET",
                    quoteOrderQty=usdt_amount) if side=="BUY" else \
                    bc.futures_create_order(symbol=s,side=side,type="MARKET",quantity=str(qty))
            elif trade_type=="margin":
                order=bc.create_margin_order(symbol=s,side=side,type="MARKET",
                    quoteOrderQty=usdt_amount) if side=="BUY" else \
                    bc.create_margin_order(symbol=s,side=side,type="MARKET",quantity=str(qty))
            else:
                order=bc.order_market_buy(symbol=s,quoteOrderQty=usdt_amount) if side=="BUY" else \
                      bc.order_market_sell(symbol=s,quantity=str(qty))
            fills=order.get("fills",[{}])
            fp=float(fills[0].get("price",price)) if fills else price
            fq=float(order.get("executedQty",qty))
            return {"ok":True,"symbol":s,"side":side,"qty":fq,"price":fp,
                    "total":fq*fp,"orderId":order.get("orderId"),"type":trade_type,"mock":False}
        except BinanceAPIException as e: return {"ok":False,"error":f"Binance: {e.message}"}
        except Exception as e: return {"ok":False,"error":str(e)}
    ep=price*random.uniform(0.999,1.001); eq=round_qty(usdt_amount/ep,step)
    return {"ok":True,"symbol":s,"side":side,"qty":eq,"price":round(ep,4),
            "total":round(usdt_amount,2),"orderId":f"DEMO-{int(time.time())}",
            "type":trade_type,"mock":True}

# ══════════════════════════════════════════════════════════════════
#  TECHNICAL ANALYSIS — Enhanced
# ══════════════════════════════════════════════════════════════════
def compute_ta(coin,interval="1h"):
    klines=get_klines(coin,interval,120)
    closes=[float(k[4]) for k in klines]
    highs=[float(k[2]) for k in klines]
    lows=[float(k[3]) for k in klines]
    volumes=[float(k[5]) for k in klines]

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

    def atr(highs,lows,closes,n=14):
        trs=[max(highs[i]-lows[i],
                 abs(highs[i]-closes[i-1]),
                 abs(lows[i]-closes[i-1])) for i in range(1,len(closes))]
        return round(sum(trs[-n:])/n,4) if trs else 0

    # RSI
    rsi_v=rsi(closes)

    # MACD
    e12=ema(closes,12); e26=ema(closes,26)
    n=min(len(e12),len(e26)); ml=[e12[-n+i]-e26[i] for i in range(n)]
    hist=ml[-1]-ema(ml,9)[-1]

    # Bollinger Bands
    p20=closes[-20:]; sma20=sum(p20)/20
    std20=math.sqrt(sum((c-sma20)**2 for c in p20)/20)
    bb_u=sma20+2*std20; bb_l=sma20-2*std20

    # EMA
    e50=ema(closes,50); e200=ema(closes,200) if len(closes)>=200 else ema(closes,len(closes))

    # Volume analysis
    avg_vol=sum(volumes[-20:])/20
    cur_vol=volumes[-1]
    vol_ratio=cur_vol/avg_vol if avg_vol else 1

    # ATR
    atr_v=atr(highs,lows,closes)

    # Stochastic RSI approximation
    rsi_vals=[rsi(closes[max(0,i-14):i+1]) for i in range(len(closes)-14,len(closes))]
    stoch_rsi=round((rsi_v-min(rsi_vals))/(max(rsi_vals)-min(rsi_vals)+0.001)*100,1) if rsi_vals else 50

    cur=closes[-1]; score=0

    # RSI signals
    if rsi_v<25:      score+=3
    elif rsi_v<35:    score+=2
    elif rsi_v>75:    score-=3
    elif rsi_v>65:    score-=2

    # MACD
    if hist>0:         score+=1
    else:              score-=1

    # Bollinger Bands
    if cur<bb_l:       score+=2
    elif cur>bb_u:     score-=2

    # EMA trend
    if e12[-1]>e26[-1]:score+=1
    else:              score-=1
    if len(e50)>0 and cur>e50[-1]: score+=1
    else:              score-=1

    # Volume confirmation
    if vol_ratio>1.5 and hist>0:  score+=1
    elif vol_ratio>1.5 and hist<0:score-=1

    # Stoch RSI
    if stoch_rsi<20:   score+=1
    elif stoch_rsi>80: score-=1

    if score>=5:    sig="🟢 СИЛЬНАЯ ПОКУПКА"
    elif score>=3:  sig="🟩 ПОКУПКА"
    elif score>=1:  sig="🟦 СЛАБАЯ ПОКУПКА"
    elif score<=-5: sig="🔴 СИЛЬНАЯ ПРОДАЖА"
    elif score<=-3: sig="🟥 ПРОДАЖА"
    elif score<=-1: sig="🟧 СЛАБАЯ ПРОДАЖА"
    else:           sig="🟡 НЕЙТРАЛЬНО"

    return {"rsi":rsi_v,"hist":round(hist,4),"signal":sig,"score":score,
            "bb_u":round(bb_u,4),"bb_l":round(bb_l,4),"bb_m":round(sma20,4),
            "ema12":round(e12[-1],4),"ema26":round(e26[-1],4),
            "ema50":round(e50[-1],4),"atr":atr_v,
            "vol_ratio":round(vol_ratio,2),"stoch_rsi":stoch_rsi,
            "price":cur}

def fear_greed():
    v=random.randint(18,88)
    i=0 if v<25 else 1 if v<45 else 2 if v<55 else 3 if v<75 else 4
    return {"value":v,
            "label":("Крайний страх","Страх","Нейтрально","Жадность","Крайняя жадность")[i],
            "emoji":("😱","😨","😐","😏","🤑")[i]}

# ── CRYPTO NEWS (Russian, mock with real topics) ──────────────────
CRYPTO_NEWS = [
    ("🔴","Bitcoin корректируется после достижения исторического максимума — аналитики ждут отката"),
    ("🟢","Ethereum готовится к обновлению — разработчики подтвердили дату"),
    ("🟡","SEC рассматривает новые заявки на крипто ETF — рынок реагирует ростом"),
    ("🔴","Крупный кит перевёл 10,000 BTC на биржу — возможное давление на продажу"),
    ("🟢","Binance объявляет о листинге новых токенов в следующем квартале"),
    ("🟡","Федеральная резервная система намекает на снижение ставок — криптовалюты растут"),
    ("🟢","Dogecoin вырос на 15% после твита крупного инфлюенсера"),
    ("🔴","Регуляторы Китая ужесточают контроль над крипто-транзакциями"),
    ("🟢","Solana обрабатывает рекордное количество транзакций — сеть стабильна"),
    ("🟡","XRP выигрывает судебное дело — Ripple освобождена от части обвинений"),
    ("🟢","Институциональные инвесторы увеличивают позиции в Bitcoin на 40%"),
    ("🔴","Майнеры продают BTC после халвинга — временное давление на цену"),
]

def get_news(count=5):
    random.shuffle(CRYPTO_NEWS)
    return CRYPTO_NEWS[:count]

# ══════════════════════════════════════════════════════════════════
#  PORTFOLIO & PnL
# ══════════════════════════════════════════════════════════════════
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
            lines.append(f"💠 *{asset}*: `{qty:.6f}` | `${val:.2f}`\n")
    if usdt>0: lines.append(f"💵 *USDT*: `${usdt:.4f}`"); tc+=usdt
    if not has and usdt==0: return "📂 *Портфель пуст*\n\nПополните счёт."
    lines.append("─────────────────")
    lines.append(f"💎 *Итого:* `${tc:.2f} USDT`")
    if ti>0:
        tp=tc-ti; te="🟢" if tp>=0 else "🔴"
        lines.append(f"{te} *PnL:* `{'+' if tp>=0 else ''}{tp:.2f}$` ({tp/ti*100:+.1f}%)")
    # Risk check
    data=USER_DATA[uid]
    if ti>0 and data.get("risk_max_loss"):
        loss_pct=(ti-tc)/ti*100 if tc<ti else 0
        if loss_pct>data["risk_max_loss"]*0.8:
            lines.append(f"\n⚠️ *Внимание!* Убыток `{loss_pct:.1f}%` близок к лимиту `{data['risk_max_loss']}%`")
    return "\n".join(lines)

def pnl_stats_text(uid):
    orders=USER_DATA[uid]["orders"]
    real=get_real_trades()
    all_orders=real if real else orders
    if not all_orders:
        return "📈 *PnL СТАТИСТИКА*\n\nНет данных. Совершите сделки!"
    buys=[o for o in all_orders if o["side"]=="BUY"]
    sells=[o for o in all_orders if o["side"]=="SELL"]
    total_bought=sum(o["total"] for o in buys)
    total_sold=sum(o["total"] for o in sells)
    pnl=total_sold-total_bought
    lines=[
        "📈 *PnL СТАТИСТИКА*\n",
        f"📊 Всего сделок: `{len(all_orders)}`",
        f"🛒 Покупок: `{len(buys)}` на `${total_bought:.2f}`",
        f"💰 Продаж: `{len(sells)}` на `${total_sold:.2f}`",
        f"{'🟢' if pnl>=0 else '🔴'} Общий PnL: `{'+' if pnl>=0 else ''}{pnl:.2f}$`",
        "",
        "📅 *По монетам:*",
    ]
    by_coin={}
    for o in all_orders:
        s=o["symbol"]
        if s not in by_coin: by_coin[s]={"buy":0,"sell":0}
        if o["side"]=="BUY": by_coin[s]["buy"]+=o["total"]
        else: by_coin[s]["sell"]+=o["total"]
    for s,v in sorted(by_coin.items(),key=lambda x:-(x[1]["buy"]+x[1]["sell"]))[:8]:
        diff=v["sell"]-v["buy"]
        e="🟢" if diff>0 else "🔴" if diff<0 else "⚪"
        lines.append(f"  {e} *{s}*: `{'+' if diff>=0 else ''}{diff:.2f}$`")
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
        # Track profit
        avg=USER_DATA[uid]["portfolio"].get(s,{}).get("avg_price",p)
        profit=(p-avg)*qty
        USER_DATA[uid]["total_profit"]+=profit

def record_order(uid,order,note=""):
    USER_DATA[uid]["orders"].insert(0,{
        "time":datetime.now().strftime("%d.%m %H:%M"),
        "symbol":order["symbol"],"side":order["side"],
        "qty":order["qty"],"price":order["price"],
        "total":order["total"],"type":order.get("type","spot"),"note":note})
    USER_DATA[uid]["orders"]=USER_DATA[uid]["orders"][:50]
    # Invalidate balance cache after trade
    global _balance_cache_ts
    _balance_cache_ts=0

# ══════════════════════════════════════════════════════════════════
#  RISK MANAGEMENT
# ══════════════════════════════════════════════════════════════════
def check_risk(uid, amount) -> tuple:
    """Returns (ok, reason)"""
    data=USER_DATA[uid]
    bals=get_real_balance(); bals.pop("_error",None); bals.pop("_mock",None)
    usdt=bals.get("USDT",0)

    # Check enough USDT
    if amount>usdt:
        return False, f"Недостаточно USDT. Доступно: ${usdt:.2f}"

    # Check max trade size
    if amount>data["risk_max_trade"]:
        return False, f"Превышен лимит сделки ${data['risk_max_trade']}"

    # Check total loss
    if data["risk_max_loss"]>0:
        port=data["portfolio"]
        ti=tc=0.0
        for s,pos in port.items():
            t=get_price(s)
            if "error" not in t:
                ti+=pos["qty"]*pos["avg_price"]
                tc+=pos["qty"]*t["price"]
        if ti>0:
            loss_pct=(ti-tc)/ti*100
            if loss_pct>=data["risk_max_loss"]:
                return False, f"Достигнут лимит убытка {data['risk_max_loss']}% — торговля заблокирована"

    return True, ""

# ══════════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════════
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Купить",        callback_data="m_buy"),
         InlineKeyboardButton("💰 Продать",       callback_data="m_sell")],
        [InlineKeyboardButton("📋 Лимит/SL/TP",   callback_data="m_limit"),
         InlineKeyboardButton("🤖 Авто-трейд",    callback_data="m_auto")],
        [InlineKeyboardButton("🔄 DCA Бот",        callback_data="m_dca"),
         InlineKeyboardButton("🎯 Grid Бот",       callback_data="m_grid")],
        [InlineKeyboardButton("💼 Портфель",       callback_data="m_portfolio"),
         InlineKeyboardButton("📈 PnL Стат.",      callback_data="m_pnl")],
        [InlineKeyboardButton("📊 Анализ",         callback_data="m_analysis"),
         InlineKeyboardButton("📉 График",         web_app=WebAppInfo(url=CHART_URL))],
        [InlineKeyboardButton("💹 Цены",           callback_data="m_prices"),
         InlineKeyboardButton("📋 Скринер",        callback_data="m_screener")],
        [InlineKeyboardButton("🔔 Алерты",         callback_data="m_alerts"),
         InlineKeyboardButton("📖 Сделки",         callback_data="m_orders")],
        [InlineKeyboardButton("📰 Новости",        callback_data="m_news"),
         InlineKeyboardButton("💱 Конвертер",      callback_data="m_convert")],
        [InlineKeyboardButton("😱 Страх/Жадн.",    callback_data="m_fg"),
         InlineKeyboardButton("🐋 Киты",           callback_data="m_whale")],
        [InlineKeyboardButton("⚙️ Риск/Настройки", callback_data="m_settings"),
         InlineKeyboardButton("💳 Баланс",         callback_data="m_balance")],
        [InlineKeyboardButton("ℹ️ Помощь",          callback_data="m_help")],
    ])

def back(t="m_main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад",callback_data=t)]])

def coins_kb(act,back_cb="m_main"):
    rows=[]; row=[]
    for c in TOP_COINS:
        row.append(InlineKeyboardButton(c,callback_data=f"{act}__{c}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Назад",callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)

def sizes_kb(act,coin,back_cb):
    rows=[]; row=[]
    for s in TRADE_SIZES:
        row.append(InlineKeyboardButton(f"${s}",callback_data=f"{act}__{coin}__{s}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("✏️ Своя сумма",callback_data=f"custom__{act}__{coin}")])
    rows.append([InlineKeyboardButton("🔙 Назад",callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)

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
        [InlineKeyboardButton("🔍 Сканировать сейчас",callback_data="auto_scan")],
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
    ve="🔥" if ta["vol_ratio"]>1.5 else "📊"
    return (f"🔬 *Анализ {coin}USDT [{iv}]*\n\n"
            f"💵 Цена: `${price:,.4f}`\n\n"
            f"📉 *RSI(14):* {re} `{ta['rsi']}`\n"
            f"   {'Перепродан 🔥' if ta['rsi']<30 else ('Перекуплен ❄️' if ta['rsi']>70 else 'Норма')}\n\n"
            f"📊 *MACD:* {me} hist=`{ta['hist']}`\n"
            f"📐 *Stoch RSI:* `{ta['stoch_rsi']}`\n\n"
            f"📏 *Bollinger:*\n"
            f"   Верх `{ta['bb_u']}` | Ср `{ta['bb_m']}` | Низ `{ta['bb_l']}`\n\n"
            f"📐 *EMA 12/26/50:* `{ta['ema12']}` / `{ta['ema26']}` / `{ta['ema50']}`\n"
            f"{ve} *Объём:* x`{ta['vol_ratio']}` от среднего\n"
            f"📏 *ATR:* `{ta['atr']}`\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🎯 Сигнал: {ta['signal']}\n"
            f"📌 Оценка: `{ta['score']}/10`")

# ══════════════════════════════════════════════════════════════════
#  TRADE CORE
# ══════════════════════════════════════════════════════════════════
async def do_trade(source,ctx,coin,side,amount,
                   confirmed=False,ttype="spot",note=""):
    if isinstance(source,int):
        uid=source; chat_id=USER_DATA[uid]["chat_id"]
        is_cb=False; upd=None
    else:
        upd=source; uid=upd.effective_user.id
        chat_id=upd.effective_chat.id
        is_cb=upd.callback_query is not None
        USER_DATA[uid]["chat_id"]=chat_id

    # Risk check for BUY
    if side=="BUY" and not confirmed:
        ok,reason=check_risk(uid,amount)
        if not ok:
            msg=f"⚠️ *Риск-менеджмент:*\n{reason}"
            if is_cb: await upd.callback_query.edit_message_text(msg,parse_mode=ParseMode.MARKDOWN)
            elif upd: await upd.message.reply_text(msg,parse_mode=ParseMode.MARKDOWN)
            return

    t=get_price(coin)
    if "error" in t:
        msg=f"❌ Нет цены {coin}: {t['error']}"
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
              f"⏳ *Авто через {AUTO_CONFIRM_TIMEOUT}с*")
        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"✅ ДА — {'КУПИТЬ' if side=='BUY' else 'ПРОДАТЬ'} ${amount}",
                callback_data=f"oktr__{side.lower()}__{coin.upper()}__{amount}__{ttype}"),
             InlineKeyboardButton("❌ Отмена",callback_data="cancel_trade")],
            [InlineKeyboardButton(f"⏳ Авто через {AUTO_CONFIRM_TIMEOUT}с",callback_data="noop")],
        ])
        if is_cb:
            await upd.callback_query.edit_message_text(text,parse_mode=ParseMode.MARKDOWN,reply_markup=kb)
            mid=upd.callback_query.message.message_id
        else:
            sent=await upd.message.reply_text(text,parse_mode=ParseMode.MARKDOWN,reply_markup=kb)
            mid=sent.message_id
        USER_DATA[uid]["pending_trade"]={"coin":coin,"side":side,"amount":amount,
                                          "msg_id":mid,"timestamp":time.time(),
                                          "chat_id":chat_id,"ttype":ttype}
        ctx.job_queue.run_once(_auto_job_confirm,when=AUTO_CONFIRM_TIMEOUT,
                               data={"uid":uid,"coin":coin,"side":side,
                                     "amount":amount,"msg_id":mid,"ttype":ttype},
                               name=f"autoconfirm_{uid}")
        return

    order=place_order(coin,side,amount,ttype)
    USER_DATA[uid]["pending_trade"]=None
    if not order["ok"]:
        await ctx.bot.send_message(chat_id,f"❌ *Ошибка:*\n`{order['error']}`",
                                   parse_mode=ParseMode.MARKDOWN); return
    update_portfolio(uid,order); record_order(uid,order,note)
    mt=" _(Демо)_" if order.get("mock") else (" _(Testnet)_" if USE_TESTNET else "")
    se="🛒 КУПЛЕНО" if side=="BUY" else "💰 ПРОДАНО"

    if side=="BUY":
        ep=order["price"]
        sl_price=round(ep*0.97,6); tp_price=round(ep*1.05,6)
        coin_clean=order["symbol"].replace("USDT","")
        sl_kb=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"✅ Да — SL -3% (${sl_price:,.4f}) + TP +5% (${tp_price:,.4f})",
                callback_data=f"set_sltp__{coin_clean}__{sl_price}__{tp_price}__{chat_id}")],
            [InlineKeyboardButton("⚙️ Своя %",
                callback_data=f"set_sltp_custom__{coin_clean}__{ep}"),
             InlineKeyboardButton("🔄 Trailing Stop",
                callback_data=f"set_trail__{coin_clean}__3"),
             InlineKeyboardButton("❌ Без",callback_data="noop")],
        ])
        await ctx.bot.send_message(chat_id,
            f"✅ *Сделка исполнена*{mt}\n\n"
            f"{se} *{order['symbol']}*\n"
            f"Тип:    {TRADE_TYPES.get(order.get('type','spot'),'')}\n"
            f"Кол-во: `{order['qty']:.6f}`\n"
            f"Цена:   `${order['price']:,.4f}`\n"
            f"Итого:  `${order['total']:.2f}`\n"
            f"ID:     `{order['orderId']}`"
            +(f"\n🤖 _{note}_" if note else "")
            +f"\n\n━━━━━━━━━━━━━━━━\n"
            f"🛡 *Установить защиту?*\n"
            f"🛑 SL: `${sl_price:,.4f}` (-3%)\n"
            f"🎯 TP: `${tp_price:,.4f}` (+5%)",
            parse_mode=ParseMode.MARKDOWN,reply_markup=sl_kb)
    else:
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

async def _auto_job_confirm(ctx):
    d=ctx.job.data; uid=d["uid"]
    if not USER_DATA[uid].get("pending_trade"): return
    chat_id=USER_DATA[uid]["chat_id"]
    try:
        await ctx.bot.edit_message_text(chat_id=chat_id,message_id=d["msg_id"],
            text=f"⏳ Авто-исполнение {d['side']} ${d['amount']} {d['coin']}...",
            parse_mode=ParseMode.MARKDOWN)
    except: pass
    await do_trade(uid,ctx,d["coin"],d["side"],d["amount"],
                   confirmed=True,ttype=d.get("ttype","spot"),
                   note=f"Авто через {AUTO_CONFIRM_TIMEOUT}с")

# ══════════════════════════════════════════════════════════════════
#  AUTO TRADE — Smart
# ══════════════════════════════════════════════════════════════════
async def do_auto_trade_direct(uid,chat_id,coin,side,amount,ta,ctx):
    USER_DATA[uid]["chat_id"]=chat_id
    t=get_price(coin); p=t.get("price",0)
    ttype=USER_DATA[uid]["auto_type"]
    se="🛒" if side=="BUY" else "💰"
    action="КУПИТЬ" if side=="BUY" else "ПРОДАТЬ"

    rows=[]; row=[]
    for s in TRADE_SIZES:
        if s>amount*1.15: continue
        row.append(InlineKeyboardButton(
            f"${s}",callback_data=f"oktr__{side.lower()}__{coin.upper()}__{s}__{ttype}"))
        if len(row)==5: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(
        f"💯 Всё: ${amount:.2f}",
        callback_data=f"oktr__{side.lower()}__{coin.upper()}__{round(amount,2)}__{ttype}")])
    rows.append([InlineKeyboardButton(
        f"⏳ Авто ${round(amount,2)} через {AUTO_CONFIRM_TIMEOUT}с",callback_data="noop")])
    rows.append([InlineKeyboardButton("❌ Пропустить",callback_data="cancel_trade")])

    msg_txt=(
        f"🤖 *Авто-сигнал*\n\n"
        f"Монета:   *{coin.upper()}USDT*\n"
        f"Тип:      {TRADE_TYPES.get(ttype,'')}\n"
        f"Цена:     `${p:,.4f}`\n"
        f"Сигнал:   {ta['signal']}\n"
        f"RSI:      `{ta['rsi']}`\n"
        f"Объём:    x`{ta.get('vol_ratio',1):.1f}` от среднего\n"
        f"Доступно: `${amount:.2f}`\n\n"
        f"{se} Предложение: *{action}*\n"
        f"Выберите сумму или ждите {AUTO_CONFIRM_TIMEOUT}с:"
    )
    sent=await ctx.bot.send_message(chat_id,msg_txt,
        parse_mode=ParseMode.MARKDOWN,reply_markup=InlineKeyboardMarkup(rows))
    USER_DATA[uid]["pending_trade"]={"coin":coin,"side":side,"amount":round(amount,2),
                                      "msg_id":sent.message_id,"timestamp":time.time(),
                                      "chat_id":chat_id,"ttype":ttype}
    ctx.job_queue.run_once(_auto_job_confirm,when=AUTO_CONFIRM_TIMEOUT,
                           data={"uid":uid,"coin":coin,"side":side,"amount":round(amount,2),
                                 "msg_id":sent.message_id,"ttype":ttype},
                           name=f"autoconfirm_{uid}")

# ══════════════════════════════════════════════════════════════════
#  COMMANDS
# ══════════════════════════════════════════════════════════════════
async def cmd_start(u,c):
    uid=u.effective_user.id; name=u.effective_user.first_name or "Трейдер"
    USER_DATA[uid]["chat_id"]=u.effective_chat.id
    live="\n⚠️ _Демо-режим_" if not bc else ("\n🟡 _Testnet_" if USE_TESTNET else "\n🟢 _LIVE торговля_")
    st="🟢 ВКЛ" if USER_DATA[uid]["auto_enabled"] else "🔴 ВЫКЛ"
    await u.message.reply_text(
        f"👋 *Добро пожаловать, {name}!*\n\n"
        f"🤖 *Binance Pro Bot v8.0*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛒 Buy/Sell | 📋 Limit/SL/TP/Trailing\n"
        f"🔄 DCA | 🎯 Grid | 🤖 Авто: {st}\n"
        f"🛡 Риск-менеджмент\n"
        f"📰 Новости на русском\n"
        f"💱 Конвертер | 📊 Ежедневный отчёт\n"
        f"📈 Сигналы: RSI+MACD+BB+EMA+Volume\n"
        f"{live}\n\n"
        f"👇 *Выберите действие:*",
        parse_mode=ParseMode.MARKDOWN,reply_markup=main_kb())

async def cmd_help(u,c):
    await u.message.reply_text(
        "📚 *КОМАНДЫ*\n\n"
        "*Торговля:*\n"
        "`/buy BTC 20` — Купить $20 BTC\n"
        "`/sell ETH 15` — Продать $15 ETH\n"
        "`/limit BTC buy 0.001 75000` — Лимит\n"
        "`/sl BTC 70000` — Stop-Loss\n"
        "`/tp BTC 85000` — Take-Profit\n"
        "`/trail BTC 3` — Trailing Stop 3%\n\n"
        "*Боты:*\n"
        "`/dca BTC 10 24` — DCA каждые 24ч\n"
        "`/grid BTC 70000 80000 10 100` — Grid\n"
        "`/auto on/off` — Авто-трейд\n"
        "`/scan` — Сканировать\n\n"
        "*Инфо:*\n"
        "`/price BTC ETH` — Цены\n"
        "`/portfolio` — Портфель\n"
        "`/pnl` — PnL статистика\n"
        "`/analysis BTC` — TA анализ\n"
        "`/news` — Новости крипто\n"
        "`/convert 1 BTC ETH` — Конвертер\n"
        "`/alert BTC above 80000` — Алерт\n"
        "`/alert BTC rsi 30` — RSI алерт\n"
        "`/alert BTC change 5` — % алерт\n"
        "`/fg` — Страх и Жадность\n"
        "`/settings` — Риск/Настройки\n",
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

async def cmd_trail(u,c):
    """Usage: /trail BTC 3  — 3% trailing stop"""
    args=c.args; uid=u.effective_user.id
    if len(args)<2:
        await u.message.reply_text("📌 `/trail BTC 3` — Trailing Stop 3%",
                                    parse_mode=ParseMode.MARKDOWN); return
    coin=args[0].upper(); pct=float(args[1])
    s=sym(coin); t=get_price(coin); price=t.get("price",0)
    USER_DATA[uid]["trailing_stops"][s]={
        "trail_pct":pct,"high_price":price,"active":True,
        "chat_id":u.effective_chat.id}
    await u.message.reply_text(
        f"🔄 *Trailing Stop установлен*\n\n"
        f"Монета:    *{s}*\n"
        f"Трейл:     `{pct}%`\n"
        f"Текущая:   `${price:,.4f}`\n"
        f"Триггер:   `${price*(1-pct/100):,.4f}`\n\n"
        f"_Stop будет подниматься вместе с ценой_",
        parse_mode=ParseMode.MARKDOWN,reply_markup=back())

async def cmd_news(u,c):
    news=get_news(6)
    lines=["📰 *Крипто-новости*\n"]
    for emoji,text in news:
        lines.append(f"{emoji} {text}\n")
    lines.append("_Обновлено: "+datetime.now().strftime("%H:%M")+"_")
    await u.message.reply_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN,
                                reply_markup=back())

async def cmd_convert(u,c):
    """Usage: /convert 1 BTC ETH  or  /convert 100 USDT BTC"""
    args=c.args
    if len(args)<3:
        await u.message.reply_text(
            "📌 `/convert 1 BTC ETH`\n`/convert 100 USDT BTC`",
            parse_mode=ParseMode.MARKDOWN); return
    amount=float(args[0]); from_c=args[1].upper(); to_c=args[2].upper()
    if from_c in ("USDT","USD"):
        t=get_price(to_c); price=t.get("price",1)
        result=amount/price
        await u.message.reply_text(
            f"💱 `{amount} USDT` = `{result:.6f} {to_c}`\n"
            f"Курс: `$1 = {1/price:.6f} {to_c}`",
            parse_mode=ParseMode.MARKDOWN)
    elif to_c in ("USDT","USD"):
        t=get_price(from_c); price=t.get("price",1)
        result=amount*price
        await u.message.reply_text(
            f"💱 `{amount} {from_c}` = `{result:.4f} USDT`\n"
            f"Курс: `1 {from_c} = ${price:,.4f}`",
            parse_mode=ParseMode.MARKDOWN)
    else:
        tf=get_price(from_c); tt=get_price(to_c)
        pf=tf.get("price",1); pt=tt.get("price",1)
        result=amount*pf/pt
        await u.message.reply_text(
            f"💱 `{amount} {from_c}` = `{result:.6f} {to_c}`\n"
            f"`1 {from_c}` = `{pf/pt:.6f} {to_c}`",
            parse_mode=ParseMode.MARKDOWN)

async def cmd_settings(u,c):
    uid=u.effective_user.id
    data=USER_DATA[uid]
    await u.message.reply_text(
        f"⚙️ *Настройки риска*\n\n"
        f"💰 Макс. сумма сделки: `${data['risk_max_trade']}`\n"
        f"📉 Макс. убыток: `{data['risk_max_loss']}%`\n"
        f"📊 Ежедневный отчёт: `{'✅ ВКЛ' if data['daily_report'] else '❌ ВЫКЛ'}`\n\n"
        f"Изменить:\n"
        f"`/set_max_trade 50` — макс $50 на сделку\n"
        f"`/set_max_loss 20` — стоп при убытке 20%\n",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Макс. сделка",  callback_data="set_risk_trade"),
             InlineKeyboardButton("📉 Макс. убыток",   callback_data="set_risk_loss")],
            [InlineKeyboardButton("📊 Отчёт ВКЛ/ВЫКЛ",callback_data="toggle_report")],
            [InlineKeyboardButton("🔙 Назад",           callback_data="m_main")]]))

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
    msg=await u.message.reply_text("🔍 Сканирование монет...")
    coins=USER_DATA[uid]["auto_coins"] or TOP_COINS
    best_coin=best_ta=None; best=0
    for coin in coins[:8]:
        ta=compute_ta(coin)
        if abs(ta["score"])>abs(best): best=ta["score"]; best_coin=coin; best_ta=ta
        await asyncio.sleep(0.3)
    if abs(best)>=3:
        await c.bot.edit_message_text(
            chat_id=u.effective_chat.id,message_id=msg.message_id,
            text=(f"🏆 Лучший сигнал: *{best_coin}USDT*\n"
                  f"Сигнал: {best_ta['signal']}\n"
                  f"RSI: `{best_ta['rsi']}` | Score: `{best_ta['score']}`\n\nТорговать?"),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Торговать",callback_data=f"autodo__{best_coin}"),
                 InlineKeyboardButton("❌ Пропустить",callback_data="m_main")]]))
    else:
        await c.bot.edit_message_text(
            chat_id=u.effective_chat.id,message_id=msg.message_id,
            text="⚪ Нет сильных сигналов.",reply_markup=back())

async def cmd_price(u,c):
    args=c.args or ["BTC","ETH","SOL","DOGE","XRP"]
    lines=["💹 *ЦЕНЫ*\n"]
    for coin in args[:6]:
        t=get_price(coin)
        if "error" in t: lines.append(f"❌ {coin}: {t['error']}")
        else:
            e="🟢" if t["change"]>=0 else "🔴"
            lines.append(f"{e} *{t['symbol']}*: `${t['price']:,.4f}` ({t['change']:+.2f}%)")
    await u.message.reply_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN)

async def cmd_portfolio(u,c):
    uid=u.effective_user.id
    await u.message.reply_text(portfolio_text(uid),parse_mode=ParseMode.MARKDOWN,reply_markup=back())

async def cmd_pnl(u,c):
    uid=u.effective_user.id
    await u.message.reply_text(pnl_stats_text(uid),parse_mode=ParseMode.MARKDOWN,reply_markup=back())

async def cmd_orders(u,c):
    uid=u.effective_user.id
    msg=await u.message.reply_text("⏳ Загружаю...")
    trades=get_real_trades()
    if trades:
        lines=[f"📖 *Сделки Binance* ({len(trades)})\n"]
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
            text="📭 *Нет сделок*\n\nСовершите первую сделку!",
            parse_mode=ParseMode.MARKDOWN,reply_markup=back()); return
    lines=["📖 *История (бот)*\n"]
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
    if err: await u.message.reply_text(f"❌ `{err}`",parse_mode=ParseMode.MARKDOWN); return
    mt=" _(Демо)_" if is_mock else ""
    lines=[f"💳 *Баланс*{mt}\n"]; total=0.0; usdt=bals.pop("USDT",0)
    if usdt>0: lines.append(f"💵 *USDT*: `${usdt:.4f}`"); total+=usdt
    for asset,qty in sorted(bals.items(),key=lambda x:-x[1]):
        t=get_price(asset)
        if "error" not in t: v=qty*t["price"]; total+=v; lines.append(f"  • *{asset}*: `{qty:.6f}` ≈ `${v:.2f}`")
        else: lines.append(f"  • *{asset}*: `{qty:.6f}`")
    lines.append(f"\n💎 *Итого ≈* `${total:.2f}`")
    lines.append(f"\n{'✅ Можно торговать' if usdt>=5 else '⚠️ Пополните USDT (мин $5)'}")
    await u.message.reply_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN,reply_markup=back())

async def cmd_analysis(u,c):
    args=c.args; coin=(args[0] if args else "BTC").upper(); iv=args[1] if len(args)>1 else "1h"
    await u.message.reply_text(f"⏳ Анализ *{coin}* [{iv}]...",parse_mode=ParseMode.MARKDOWN)
    ta=compute_ta(coin,iv); t=get_price(coin)
    await u.message.reply_text(ta_text(coin,t.get("price",0),ta,iv),parse_mode=ParseMode.MARKDOWN)

async def cmd_alert(u,c):
    uid=u.effective_user.id; args=c.args
    if len(args)<3:
        await u.message.reply_text(
            "📌 `/alert BTC above 80000`\n"
            "`/alert BTC below 70000`\n"
            "`/alert BTC rsi 30`\n"
            "`/alert BTC change 5`\n"
            "`/alert BTC volume 1000000`",
            parse_mode=ParseMode.MARKDOWN); return
    coin=args[0].upper(); cond=args[1].lower(); val=float(args[2])
    s=sym(coin)
    USER_DATA[uid]["alerts"].append({
        "symbol":s,"condition":cond,"price":val,
        "chat_id":u.effective_chat.id,"type":"custom"})
    desc={"above":f"цена ⬆️ ${val:,.2f}","below":f"цена ⬇️ ${val:,.2f}",
          "rsi":f"RSI = {val}","change":f"изм. ≥ {val}%",
          "volume":f"объём ≥ {val:,.0f}"}.get(cond,f"{cond}={val}")
    await u.message.reply_text(f"🔔 *Алерт:* *{s}* — {desc}",parse_mode=ParseMode.MARKDOWN)

async def cmd_fg(u,c):
    fg=fear_greed(); bar="█"*int(fg["value"]/5)+"░"*(20-int(fg["value"]/5))
    await u.message.reply_text(
        f"😱 *Страх и Жадность*\n```\n[{bar}]\n```\n{fg['emoji']} *{fg['value']}/100* — {fg['label']}",
        parse_mode=ParseMode.MARKDOWN)

async def cmd_dca(u,c):
    args=c.args; uid=u.effective_user.id
    if len(args)<3:
        await u.message.reply_text("📌 `/dca BTC 10 24`\ncoin | сумма$ | часов",
                                    parse_mode=ParseMode.MARKDOWN); return
    coin=args[0].upper(); amount=float(args[1]); interval_h=int(args[2])
    s=sym(coin); t=get_price(coin)
    USER_DATA[uid]["dca_bots"].append({
        "symbol":s,"amount":amount,"interval_h":interval_h,
        "next_run":time.time()+interval_h*3600,
        "active":True,"total_invested":0,"runs":0,
        "chat_id":u.effective_chat.id,"uid":uid})
    await u.message.reply_text(
        f"🔄 *DCA Бот запущен*\n\n*{s}* `${amount}` каждые `{interval_h}ч`\nСледующий: через `{interval_h}ч`",
        parse_mode=ParseMode.MARKDOWN,reply_markup=back())

async def cmd_grid(u,c):
    args=c.args; uid=u.effective_user.id
    if len(args)<5:
        await u.message.reply_text("📌 `/grid BTC 70000 80000 10 100`",
                                    parse_mode=ParseMode.MARKDOWN); return
    coin=args[0].upper(); low=float(args[1]); high=float(args[2])
    grids=int(args[3]); total=float(args[4])
    if low>=high:
        await u.message.reply_text("❌ Нижняя < верхней"); return
    s=sym(coin); step_price=(high-low)/grids; amount_per=total/grids
    USER_DATA[uid]["grid_bots"].append({
        "symbol":s,"low":low,"high":high,"grids":grids,"total":total,
        "amount_per":amount_per,"step":step_price,
        "active":True,"profit":0,"trades":0,
        "chat_id":u.effective_chat.id,"uid":uid})
    t=get_price(coin)
    await u.message.reply_text(
        f"🎯 *Grid Бот*\n\n*{s}* `${low:,.0f}`-`${high:,.0f}`\n"
        f"Сеток: `{grids}` | Шаг: `${step_price:,.2f}` | Сумма: `${total}`",
        parse_mode=ParseMode.MARKDOWN,reply_markup=back())

# ── TEXT INPUT ────────────────────────────────────────────────────
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
                f"✅ Алерт: *{sym(coin)}* {e} `${price:,.2f}`",
                parse_mode=ParseMode.MARKDOWN,reply_markup=back("m_alerts"))
        except:
            await u.message.reply_text("❌ Введите число",parse_mode=ParseMode.MARKDOWN)
        return

    if w.get("type")=="custom_sltp":
        try:
            parts_in=text.strip().split()
            if len(parts_in)<2: raise ValueError
            sl_pct=float(parts_in[0]); tp_pct=float(parts_in[1])
            if sl_pct<=0 or tp_pct<=0: raise ValueError
        except:
            await u.message.reply_text("❌ Формат: `3 5` — SL% TP%",parse_mode=ParseMode.MARKDOWN); return
        coin_c=w["coin"]; exec_price=w["exec_price"]; chat_id_t=w["chat_id"]
        sl_price=round(exec_price*(1-sl_pct/100),6); tp_price=round(exec_price*(1+tp_pct/100),6)
        s=sym(coin_c)
        USER_DATA[uid]["alerts"].append({"symbol":s,"condition":"below","price":sl_price,
                                          "chat_id":chat_id_t,"type":"sl"})
        USER_DATA[uid]["alerts"].append({"symbol":s,"condition":"above","price":tp_price,
                                          "chat_id":chat_id_t,"type":"tp"})
        USER_DATA[uid]["waiting_input"]=None
        await u.message.reply_text(
            f"✅ SL `-{sl_pct}%` = `${sl_price:,.4f}` | TP `+{tp_pct}%` = `${tp_price:,.4f}`",
            parse_mode=ParseMode.MARKDOWN,reply_markup=back())
        return

    if w.get("type")=="risk_trade":
        try:
            val=float(text.replace("$",""))
            USER_DATA[uid]["risk_max_trade"]=val
            USER_DATA[uid]["waiting_input"]=None
            await u.message.reply_text(f"✅ Макс. сделка: `${val}`",parse_mode=ParseMode.MARKDOWN,reply_markup=back())
        except:
            await u.message.reply_text("❌ Введите число",parse_mode=ParseMode.MARKDOWN)
        return

    if w.get("type")=="risk_loss":
        try:
            val=float(text.replace("%",""))
            USER_DATA[uid]["risk_max_loss"]=val
            USER_DATA[uid]["waiting_input"]=None
            await u.message.reply_text(f"✅ Макс. убыток: `{val}%`",parse_mode=ParseMode.MARKDOWN,reply_markup=back())
        except:
            await u.message.reply_text("❌ Введите число",parse_mode=ParseMode.MARKDOWN)
        return

    if w.get("type") in ("buy_amount","sell_amount","auto_size"):
        try:
            amount=float(text.replace("$","").replace(",",".")); assert amount>0
        except:
            await u.message.reply_text("❌ Введите число",parse_mode=ParseMode.MARKDOWN); return
        USER_DATA[uid]["waiting_input"]=None
        if w["type"]=="auto_size":
            USER_DATA[uid]["auto_size"]=amount
            await u.message.reply_text(f"✅ Сумма авто: `${amount}`",
                                        parse_mode=ParseMode.MARKDOWN,reply_markup=auto_kb(uid))
        else:
            side="BUY" if w["type"]=="buy_amount" else "SELL"
            await do_trade(u,c,w["coin"],side,amount,ttype=w.get("ttype",USER_DATA[uid]["auto_type"]))

# ══════════════════════════════════════════════════════════════════
#  CALLBACK HANDLER
# ══════════════════════════════════════════════════════════════════
async def cb(u,c):
    q=u.callback_query; await q.answer(); d=q.data
    uid=u.effective_user.id; USER_DATA[uid]["chat_id"]=u.effective_chat.id

    if d=="m_main":
        await q.edit_message_text("🤖 *Binance Pro Bot v8.0*\n\n👇 Выберите действие:",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=main_kb())
    elif d=="m_buy":
        await q.edit_message_text("🛒 *КУПИТЬ — Выберите монету:*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=coins_kb("buyc","m_main"))
    elif d=="m_sell":
        await q.edit_message_text("💰 *ПРОДАТЬ — Выберите монету:*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=coins_kb("sellc","m_main"))
    elif d=="m_portfolio":
        await q.edit_message_text(portfolio_text(uid),parse_mode=ParseMode.MARKDOWN,reply_markup=back())
    elif d=="m_pnl":
        await q.edit_message_text(pnl_stats_text(uid),parse_mode=ParseMode.MARKDOWN,reply_markup=back())
    elif d=="m_balance":
        bals=get_real_balance(); err=bals.pop("_error",None); is_mock=bals.pop("_mock",False)
        if err:
            await q.edit_message_text(f"❌ `{err}`",parse_mode=ParseMode.MARKDOWN,reply_markup=back()); return
        lines=[f"💳 *Баланс*{'_(Демо)_' if is_mock else ''}\n"]; total=0.0; usdt=bals.pop("USDT",0)
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
            lines=[f"📖 *Сделки* ({len(trades)})\n"]
            for o in trades[:10]:
                e="🟢" if o["side"]=="BUY" else "🔴"
                lines.append(f"{e} *{o['symbol']}* `${o['total']:.2f}` — _{o['time']}_")
            await q.edit_message_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN,reply_markup=back())
        else:
            local=USER_DATA[uid]["orders"]
            txt=("📖 *Сделки (бот)*\n\n"+"\n".join(
                f"{'🟢' if o['side']=='BUY' else '🔴'} *{o['symbol']}* `${o['total']:.2f}` — _{o['time']}_"
                for o in local[:8])) if local else "📭 *Нет сделок*"
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
        prices=get_all_prices()
        res=[(s.replace("USDT",""),v["change"],v["price"]) for s,v in prices.items() if "error" not in v]
        res.sort(key=lambda x:x[1],reverse=True)
        lines=["📋 *СКРИНЕР*\n","🟢 *Рост:*"]
        for coin,chg,pr in res[:5]: lines.append(f"  • *{coin}*: `{chg:+.2f}%` @ `${pr:,.4f}`")
        lines.append("\n🔴 *Падение:*")
        for coin,chg,pr in res[-5:]: lines.append(f"  • *{coin}*: `{chg:+.2f}%` @ `${pr:,.4f}`")
        await q.edit_message_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN,reply_markup=back())
    elif d=="m_news":
        news=get_news(6); lines=["📰 *Крипто-новости*\n"]
        for emoji,text in news: lines.append(f"{emoji} {text}\n")
        await q.edit_message_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN,reply_markup=back())
    elif d=="m_convert":
        await q.edit_message_text(
            "💱 *Конвертер*\n\nИспользуйте команду:\n"
            "`/convert 1 BTC ETH`\n`/convert 100 USDT DOGE`\n`/convert 5 ADA USDT`",
            parse_mode=ParseMode.MARKDOWN,reply_markup=back())
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
        await q.edit_message_text("📌 `/help`",parse_mode=ParseMode.MARKDOWN,reply_markup=back())

    # SETTINGS
    elif d=="m_settings":
        data=USER_DATA[uid]
        await q.edit_message_text(
            f"⚙️ *Настройки*\n\n"
            f"💰 Макс. сделка: `${data['risk_max_trade']}`\n"
            f"📉 Макс. убыток: `{data['risk_max_loss']}%`\n"
            f"📊 Ежедн. отчёт: `{'✅ ВКЛ' if data['daily_report'] else '❌ ВЫКЛ'}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Макс. сделка",  callback_data="set_risk_trade"),
                 InlineKeyboardButton("📉 Макс. убыток",   callback_data="set_risk_loss")],
                [InlineKeyboardButton("📊 Отчёт ВКЛ/ВЫКЛ",callback_data="toggle_report")],
                [InlineKeyboardButton("🔙 Назад",           callback_data="m_main")]]))
    elif d=="set_risk_trade":
        USER_DATA[uid]["waiting_input"]={"type":"risk_trade"}
        await q.edit_message_text("💰 Введите макс. сумму одной сделки в $:\nПример: `50`",
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌",callback_data="m_settings")]]))
    elif d=="set_risk_loss":
        USER_DATA[uid]["waiting_input"]={"type":"risk_loss"}
        await q.edit_message_text("📉 Введите макс. % убытка:\nПример: `20` (стоп при убытке 20%)",
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌",callback_data="m_settings")]]))
    elif d=="toggle_report":
        USER_DATA[uid]["daily_report"]=not USER_DATA[uid]["daily_report"]
        on=USER_DATA[uid]["daily_report"]
        await q.edit_message_text(f"📊 Ежедн. отчёт: *{'✅ ВКЛ' if on else '❌ ВЫКЛ'}*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=back("m_settings"))

    # LIMIT / SL / TP
    elif d=="m_limit":
        uid_lo=USER_DATA[uid]["limit_orders"]
        lines=["📋 *Лимит / SL / TP*\n"]
        if uid_lo:
            for o in uid_lo[:5]:
                e="🛒" if o["side"]=="BUY" else "💰"
                lines.append(f"{e} *{o['symbol']}* @ `${o['price']:,.4f}` — {o.get('type','LIMIT')}")
        else: lines.append("_Нет активных ордеров_")
        lines.append("\n`/limit BTC buy 0.001 75000`\n`/sl BTC 70000`\n`/tp BTC 85000`\n`/trail BTC 3`")
        await q.edit_message_text("\n".join(lines),parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛑 SL",callback_data="lmt__sl"),
                 InlineKeyboardButton("🎯 TP",callback_data="lmt__tp"),
                 InlineKeyboardButton("🔄 Trail",callback_data="lmt__trail")],
                [InlineKeyboardButton("🗑 Удалить все",callback_data="lmt__clear")],
                [InlineKeyboardButton("🔙 Назад",callback_data="m_main")]]))
    elif d=="lmt__sl":
        await q.edit_message_text("🛑 *SL — Выберите монету:*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=coins_kb("slc","m_limit"))
    elif d=="lmt__tp":
        await q.edit_message_text("🎯 *TP — Выберите монету:*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=coins_kb("tpc","m_limit"))
    elif d=="lmt__trail":
        await q.edit_message_text("🔄 *Trailing Stop*\n\nКоманда:\n`/trail BTC 3` — 3% трейлинг",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=back("m_limit"))
    elif d=="lmt__clear":
        USER_DATA[uid]["limit_orders"]=[]; USER_DATA[uid]["trailing_stops"]={}
        await q.edit_message_text("🗑 Ордера удалены.",reply_markup=back("m_main"))
    elif d.startswith("slc__"):
        coin=d.split("__")[1]; t=get_price(coin)
        USER_DATA[uid]["waiting_input"]={"type":"alert_price","coin":coin,"cond":"below"}
        await q.edit_message_text(f"🛑 *SL — {coin}USDT*\nЦена: `${t.get('price',0):,.4f}`\n\nВведите цену:",
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌",callback_data="m_limit")]]))
    elif d.startswith("tpc__"):
        coin=d.split("__")[1]; t=get_price(coin)
        USER_DATA[uid]["waiting_input"]={"type":"alert_price","coin":coin,"cond":"above"}
        await q.edit_message_text(f"🎯 *TP — {coin}USDT*\nЦена: `${t.get('price',0):,.4f}`\n\nВведите цену:",
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌",callback_data="m_limit")]]))

    # SL/TP auto-set after BUY
    elif d.startswith("set_sltp__"):
        parts=d.split("__"); coin_c=parts[1]; sl_price=float(parts[2]); tp_price=float(parts[3]); chat_id_t=int(parts[4])
        s=sym(coin_c)
        USER_DATA[uid]["alerts"].append({"symbol":s,"condition":"below","price":sl_price,"chat_id":chat_id_t,"type":"sl"})
        USER_DATA[uid]["alerts"].append({"symbol":s,"condition":"above","price":tp_price,"chat_id":chat_id_t,"type":"tp"})
        await q.edit_message_text(
            f"✅ *SL/TP установлены!*\n\n🛑 SL: `${sl_price:,.4f}` (-3%)\n🎯 TP: `${tp_price:,.4f}` (+5%)\n\n_Бот уведомит и авто-продаст при достижении_",
            parse_mode=ParseMode.MARKDOWN,reply_markup=back())
    elif d.startswith("set_sltp_custom__"):
        parts=d.split("__"); coin_c=parts[1]; exec_price=float(parts[2])
        USER_DATA[uid]["waiting_input"]={"type":"custom_sltp","coin":coin_c,"exec_price":exec_price,"chat_id":u.effective_chat.id}
        await q.edit_message_text(
            f"⚙️ *SL/TP — {coin_c}*\nЦена: `${exec_price:,.4f}`\n\nВведите `SL% TP%`:\nПример: `3 5` = SL-3% TP+5%",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌",callback_data="m_main")]]))
    elif d.startswith("set_trail__"):
        parts=d.split("__"); coin_c=parts[1]; pct=float(parts[2])
        s=sym(coin_c); t=get_price(coin_c); price=t.get("price",0)
        USER_DATA[uid]["trailing_stops"][s]={"trail_pct":pct,"high_price":price,"active":True,"chat_id":u.effective_chat.id}
        await q.edit_message_text(
            f"🔄 *Trailing Stop*\n\n*{s}* `{pct}%`\nТек. цена: `${price:,.4f}`",
            parse_mode=ParseMode.MARKDOWN,reply_markup=back())

    # DCA
    elif d=="m_dca":
        bots=[b for b in USER_DATA[uid]["dca_bots"] if b.get("active")]
        if not bots: txt="🔄 *DCA Бот*\n\n_Нет активных_\n\n`/dca BTC 10 24`"
        else:
            lines=["🔄 *DCA Боты*\n"]
            for b in bots:
                nxt=datetime.fromtimestamp(b["next_run"]).strftime("%d.%m %H:%M")
                lines.append(f"• *{b['symbol']}* `${b['amount']}` / `{b['interval_h']}ч` → `{nxt}`")
            txt="\n".join(lines)
        await q.edit_message_text(txt,parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Новый",callback_data="dca__new")],
                [InlineKeyboardButton("⏹ Стоп все",callback_data="dca__stop")],
                [InlineKeyboardButton("🔙 Назад",callback_data="m_main")]]))
    elif d=="dca__new":
        await q.edit_message_text("📌 `/dca BTC 10 24`\ncoin | сумма$ | часов",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=back("m_dca"))
    elif d=="dca__stop":
        for b in USER_DATA[uid]["dca_bots"]: b["active"]=False
        await q.edit_message_text("⏹ Все DCA остановлены.",reply_markup=back("m_main"))

    # GRID
    elif d=="m_grid":
        bots=[b for b in USER_DATA[uid]["grid_bots"] if b.get("active")]
        if not bots: txt="🎯 *Grid Бот*\n\n_Нет активных_\n\n`/grid BTC 70000 80000 10 100`"
        else:
            lines=["🎯 *Grid Боты*\n"]
            for b in bots:
                lines.append(f"• *{b['symbol']}* `${b['low']:,.0f}`-`${b['high']:,.0f}` | Сделок: `{b['trades']}`")
            txt="\n".join(lines)
        await q.edit_message_text(txt,parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Новый",callback_data="grid__new")],
                [InlineKeyboardButton("⏹ Стоп все",callback_data="grid__stop")],
                [InlineKeyboardButton("🔙 Назад",callback_data="m_main")]]))
    elif d=="grid__new":
        await q.edit_message_text("📌 `/grid BTC 70000 80000 10 100`",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=back("m_grid"))
    elif d=="grid__stop":
        for b in USER_DATA[uid]["grid_bots"]: b["active"]=False
        await q.edit_message_text("⏹ Все Grid остановлены.",reply_markup=back("m_main"))

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
        await q.edit_message_text(f"🛒 *{coin}USDT*\n`${t.get('price',0):,.4f}`\n\nВыберите сумму:",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=sizes_kb("buy",coin,"m_buy"))
    elif d.startswith("sellc__"):
        coin=d.split("__")[1]; t=get_price(coin)
        await q.edit_message_text(f"💰 *{coin}USDT*\n`${t.get('price',0):,.4f}`\n\nВыберите сумму:",
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
        await q.edit_message_text(f"✏️ *Своя сумма — {coin}*\n\nВведите $:",
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌",callback_data="m_main")]]))
    elif d.startswith("custom__sell__"):
        coin=d.split("__")[2]
        USER_DATA[uid]["waiting_input"]={"type":"sell_amount","coin":coin,"ttype":USER_DATA[uid]["auto_type"]}
        await q.edit_message_text(f"✏️ *Своя сумма — {coin}*\n\nВведите $:",
                                   parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌",callback_data="m_main")]]))

    # CONFIRM
    elif d.startswith("oktr__"):
        parts=d.split("__"); side=parts[1].upper(); coin=parts[2]
        amount=float(parts[3]); ttype=parts[4] if len(parts)>4 else "spot"
        for j in c.job_queue.get_jobs_by_name(f"autoconfirm_{uid}"): j.schedule_removal()
        USER_DATA[uid]["pending_trade"]=None
        await do_trade(u,c,coin,side,amount,confirmed=True,ttype=ttype,note="Пользователь подтвердил")
    elif d=="cancel_trade":
        for j in c.job_queue.get_jobs_by_name(f"autoconfirm_{uid}"): j.schedule_removal()
        USER_DATA[uid]["pending_trade"]=None
        await q.edit_message_text("❌ Сделка отменена.",reply_markup=back())

    # AUTO
    elif d=="m_auto":
        on=USER_DATA[uid]["auto_enabled"]
        await q.edit_message_text(
            f"🤖 *Авто-Трейд*\n\nСтатус: *{'🟢 ВКЛ' if on else '🔴 ВЫКЛ'}*\n"
            f"Тип: {TRADE_TYPES.get(USER_DATA[uid]['auto_type'],'')}\n"
            f"Сумма: `${USER_DATA[uid]['auto_size']}`\n"
            f"Монет: `{len(USER_DATA[uid]['auto_coins'])}/15`\n\n"
            f"_Сканирует баланс и открытые позиции_\n"
            f"_BUY только при наличии USDT_\n"
            f"_SELL только при наличии монеты_",
            parse_mode=ParseMode.MARKDOWN,reply_markup=auto_kb(uid))
    elif d=="auto_toggle":
        USER_DATA[uid]["auto_enabled"]=not USER_DATA[uid]["auto_enabled"]
        on=USER_DATA[uid]["auto_enabled"]
        await q.edit_message_text(f"🤖 *{'🟢 ВКЛЮЧЁН' if on else '🔴 ВЫКЛЮЧЕН'}*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=auto_kb(uid))
    elif d=="auto_type":
        await q.edit_message_text("🔧 *Тип:*",parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([
                                       [InlineKeyboardButton("📈 Спот",callback_data="atype__spot")],
                                       [InlineKeyboardButton("🔮 Фьючерсы",callback_data="atype__futures")],
                                       [InlineKeyboardButton("💳 Маржа",callback_data="atype__margin")],
                                       [InlineKeyboardButton("🔙",callback_data="m_auto")]]))
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
        rows.append([InlineKeyboardButton("✏️ Своя",callback_data="asize__custom")])
        rows.append([InlineKeyboardButton("🔙",callback_data="m_auto")])
        await q.edit_message_text("💵 *Сумма авто:*",parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup(rows))
    elif d.startswith("asize__"):
        val=d.split("__")[1]
        if val=="custom":
            USER_DATA[uid]["waiting_input"]={"type":"auto_size","coin":"","ttype":""}
            await q.edit_message_text("✏️ Введите сумму $:",parse_mode=ParseMode.MARKDOWN,
                                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌",callback_data="m_auto")]]))
        else:
            USER_DATA[uid]["auto_size"]=float(val)
            await q.edit_message_text(f"✅ Сумма: `${val}`",parse_mode=ParseMode.MARKDOWN,reply_markup=auto_kb(uid))
    elif d=="auto_coins":
        await q.edit_message_text("🪙 *Монеты:*",parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=auto_coins_kb(uid))
    elif d.startswith("acoin__"):
        val=d.split("__")[1]
        if val=="ALL": USER_DATA[uid]["auto_coins"]=list(TOP_COINS)
        elif val=="NONE": USER_DATA[uid]["auto_coins"]=[]
        else:
            coins=USER_DATA[uid]["auto_coins"]
            if val in coins: coins.remove(val)
            else: coins.append(val)
        await q.edit_message_text("🪙",parse_mode=ParseMode.MARKDOWN,reply_markup=auto_coins_kb(uid))
    elif d=="auto_scan":
        await q.edit_message_text("🔍 Сканирование...")
        coins=USER_DATA[uid]["auto_coins"] or TOP_COINS
        best_coin=best_ta=None; best=0
        for coin in coins[:8]:
            ta=compute_ta(coin)
            if abs(ta["score"])>abs(best): best=ta["score"]; best_coin=coin; best_ta=ta
            await asyncio.sleep(0.3)
        if abs(best)>=3:
            await q.edit_message_text(
                f"🏆 *{best_coin}USDT* — {best_ta['signal']}\nRSI:`{best_ta['rsi']}` Score:`{best_ta['score']}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 Торговать",callback_data=f"autodo__{best_coin}"),
                     InlineKeyboardButton("❌",callback_data="m_auto")]]))
        else:
            await q.edit_message_text("⚪ Нет сигналов.",reply_markup=back("m_auto"))
    elif d.startswith("autodo__"):
        coin=d.split("__")[1]
        bals=get_real_balance(); bals.pop("_error",None); bals.pop("_mock",None)
        usdt=bals.get("USDT",0); ta=compute_ta(coin)
        if ta["score"]>=3:
            amount=min(USER_DATA[uid]["auto_size"],usdt*0.95)
            if amount>=5: await do_auto_trade_direct(uid,u.effective_chat.id,coin,"BUY",amount,ta,c)
            else: await q.edit_message_text(f"⚠️ Недостаточно USDT (${usdt:.2f})",reply_markup=back("m_auto"))
        else:
            await q.edit_message_text(f"⚪ Слабый сигнал для {coin}.",reply_markup=back("m_auto"))

    # ALERTS
    elif d=="m_alerts":
        alerts=USER_DATA[uid]["alerts"]
        if not alerts: txt="🔕 *Алерты*\n\nНет алертов."
        else:
            lines=["🔔 *Алерты:*\n"]
            for i,a in enumerate(alerts,1):
                icons={"above":"⬆️","below":"⬇️","rsi":"📉","change":"📊","volume":"📈"}
                e=icons.get(a["condition"],"🔔")
                tag=" _[SL]_" if a.get("type")=="sl" else " _[TP]_" if a.get("type")=="tp" else ""
                lines.append(f"`{i}.` *{a['symbol']}* {e} `{a['price']}`{tag}")
            txt="\n".join(lines)
        await q.edit_message_text(txt,parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup([
                                       [InlineKeyboardButton("➕ Цена",callback_data="alert_add"),
                                        InlineKeyboardButton("📊 RSI",callback_data="alert_rsi"),
                                        InlineKeyboardButton("📈 %",callback_data="alert_chg")],
                                       [InlineKeyboardButton("🗑 Удалить все",callback_data="alert_clear")],
                                       [InlineKeyboardButton("🔙 Назад",callback_data="m_main")]]))
    elif d=="alert_add":
        await q.edit_message_text("🔔 *Выберите монету:*",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=coins_kb("alertc","m_alerts"))
    elif d=="alert_rsi":
        await q.edit_message_text("📉 `/alert BTC rsi 30` — RSI ≤ 30",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=back("m_alerts"))
    elif d=="alert_chg":
        await q.edit_message_text("📊 `/alert BTC change 5` — изм. ≥ 5%",
                                   parse_mode=ParseMode.MARKDOWN,reply_markup=back("m_alerts"))
    elif d.startswith("alertc__"):
        coin=d.split("__")[1]; t=get_price(coin)
        await q.edit_message_text(
            f"🔔 *{coin}USDT* `${t.get('price',0):,.4f}`\n\nУсловие:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬆️ Выше",callback_data=f"alertcond__{coin}__above"),
                 InlineKeyboardButton("⬇️ Ниже",callback_data=f"alertcond__{coin}__below")],
                [InlineKeyboardButton("🔙",callback_data="alert_add")]]))
    elif d.startswith("alertcond__"):
        parts=d.split("__"); coin=parts[1]; cond=parts[2]
        USER_DATA[uid]["waiting_input"]={"type":"alert_price","coin":coin,"cond":cond}
        t=get_price(coin)
        await q.edit_message_text(
            f"🔔 *{coin}USDT — {'выше' if cond=='above' else 'ниже'}*\n`${t.get('price',0):,.4f}`\n\nВведите цену:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌",callback_data="m_alerts")]]))
    elif d=="alert_clear":
        USER_DATA[uid]["alerts"]=[]
        await q.edit_message_text("🗑 Удалены.",reply_markup=back("m_main"))
    elif d=="noop": pass

# ══════════════════════════════════════════════════════════════════
#  BACKGROUND JOBS
# ══════════════════════════════════════════════════════════════════
async def alerts_job(ctx):
    """Check all alerts + SL/TP auto-execute + trailing stops."""
    for uid,data in list(USER_DATA.items()):
        triggered,remaining=[],[]
        ta_cache={}

        for alert in data.get("alerts",[]):
            s=alert["symbol"]; cond=alert["condition"]
            t=get_price(s)
            if "error" in t: remaining.append(alert); continue
            p=t["price"]; chg=t.get("change",0); hit=False

            if cond=="above":   hit=p>=alert["price"]
            elif cond=="below": hit=p<=alert["price"]
            elif cond=="change": hit=abs(chg)>=alert["price"]
            elif cond=="rsi":
                if s not in ta_cache: ta_cache[s]=compute_ta(s)
                rsi_v=ta_cache[s]["rsi"]
                hit=rsi_v<=alert["price"] or rsi_v>=(100-alert["price"])
            elif cond=="volume": hit=t.get("volume",0)>=alert["price"]

            if hit: triggered.append((alert,p,t))
            else:   remaining.append(alert)

        data["alerts"]=remaining

        for alert,cur,ticker in triggered:
            atype=alert.get("type",""); chat_id=alert.get("chat_id")
            s=alert["symbol"]; coin_clean=s.replace("USDT","")

            # AUTO EXECUTE SL/TP
            if atype in ("sl","tp") and data.get("auto_enabled") and chat_id:
                bals=get_real_balance(); bals.pop("_error",None); bals.pop("_mock",None)
                coin_qty=bals.get(coin_clean,0)
                if coin_qty>0.000001:
                    sell_val=coin_qty*cur*0.99
                    if sell_val>=5:
                        tag="🛑 STOP-LOSS" if atype=="sl" else "🎯 TAKE-PROFIT"
                        try:
                            order=place_order(coin_clean,"SELL",sell_val)
                            if order["ok"]:
                                update_portfolio(uid,order); record_order(uid,order,note=tag)
                                await ctx.bot.send_message(chat_id,
                                    f"{'🛑' if atype=='sl' else '🎯'} *{tag} ИСПОЛНЕН!*\n\n"
                                    f"Монета: *{s}*\n"
                                    f"Продано: `{order['qty']:.6f}`\n"
                                    f"Цена:   `${order['price']:,.4f}`\n"
                                    f"Итого:  `${order['total']:.2f}`",
                                    parse_mode=ParseMode.MARKDOWN,reply_markup=back())
                                continue
                        except Exception as e:
                            log.error(f"SL/TP execute error: {e}")

            # Notify only
            if chat_id:
                icons={"above":"⬆️","below":"⬇️","rsi":"📉","change":"📊","volume":"📈"}
                e=icons.get(alert["condition"],"🔔")
                tag_txt=" 🛑 SL" if atype=="sl" else " 🎯 TP" if atype=="tp" else ""
                try:
                    await ctx.bot.send_message(chat_id,
                        f"🔔 *АЛЕРТ{tag_txt}!*\n\n"
                        f"*{s}* {e}\n"
                        f"Условие: `{alert['condition']}` = `{alert['price']}`\n"
                        f"Текущая: `${cur:,.4f}` ({ticker.get('change',0):+.2f}%)",
                        parse_mode=ParseMode.MARKDOWN)
                except Exception as err: log.error(f"Alert notify: {err}")

        # ── Trailing Stop ─────────────────────────────────────
        for s,ts in list(data.get("trailing_stops",{}).items()):
            if not ts.get("active"): continue
            t=get_price(s)
            if "error" in t: continue
            price=t["price"]
            if price>ts["high_price"]:
                ts["high_price"]=price  # raise the high
            trigger=ts["high_price"]*(1-ts["trail_pct"]/100)
            if price<=trigger:
                ts["active"]=False
                coin_clean=s.replace("USDT","")
                bals=get_real_balance(); bals.pop("_error",None); bals.pop("_mock",None)
                coin_qty=bals.get(coin_clean,0)
                chat_id=ts.get("chat_id") or data.get("chat_id")
                if coin_qty>0.000001 and chat_id:
                    sell_val=coin_qty*price*0.99
                    if sell_val>=5:
                        try:
                            order=place_order(coin_clean,"SELL",sell_val)
                            if order["ok"]:
                                update_portfolio(uid,order)
                                record_order(uid,order,note="Trailing Stop")
                                await ctx.bot.send_message(chat_id,
                                    f"🔄 *TRAILING STOP ИСПОЛНЕН!*\n\n"
                                    f"*{s}*\n"
                                    f"Пик: `${ts['high_price']:,.4f}`\n"
                                    f"Триггер: `${trigger:,.4f}` (-{ts['trail_pct']}%)\n"
                                    f"Продано: `{order['qty']:.6f}` @ `${order['price']:,.4f}`\n"
                                    f"Итого: `${order['total']:.2f}`",
                                    parse_mode=ParseMode.MARKDOWN,reply_markup=back())
                        except Exception as e: log.error(f"Trail execute: {e}")

async def auto_job(ctx):
    """Smart auto-trade — balance aware."""
    for uid,data in list(USER_DATA.items()):
        if not data.get("auto_enabled"): continue
        if not data.get("chat_id"):      continue
        if data.get("pending_trade"):    continue

        bals=get_real_balance(); bals.pop("_error",None); bals.pop("_mock",None)
        usdt=bals.get("USDT",0)
        held_coins=[a for a,q in bals.items() if a!="USDT" and a in TOP_COINS and q>0.000001]
        has_usdt=usdt>=5

        # Risk check
        ok,reason=check_risk(uid,data["auto_size"])
        if not ok and "баланс" not in reason.lower():
            continue  # stop all trading if risk exceeded

        # SELL scan — only held coins
        best_sell=None; best_sell_ta=None; best_sell_score=0
        for asset in held_coins:
            ta=compute_ta(asset)
            if ta["score"]<=-3 and abs(ta["score"])>abs(best_sell_score):
                best_sell_score=ta["score"]; best_sell=asset; best_sell_ta=ta
            await asyncio.sleep(0.5)

        if best_sell and best_sell_ta:
            t=get_price(best_sell); price=t.get("price",0)
            qty=bals.get(best_sell,0); sell_val=qty*price*0.99
            amount=min(data["auto_size"],sell_val)
            if amount>=5:
                await do_auto_trade_direct(uid,data["chat_id"],best_sell,"SELL",amount,best_sell_ta,ctx)
                await asyncio.sleep(2); continue

        # BUY scan — only if has USDT
        if has_usdt:
            coins=data["auto_coins"] or TOP_COINS
            # Rotate coins to avoid always scanning same ones
            idx=data.get("scan_idx",0)
            scan=coins[idx:idx+5] or coins[:5]
            data["scan_idx"]=(idx+5)%max(len(coins),1)

            best_buy=None; best_buy_ta=None; best_buy_score=0
            for coin in scan:
                ta=compute_ta(coin)
                if ta["score"]>=3 and ta["score"]>best_buy_score:
                    best_buy_score=ta["score"]; best_buy=coin; best_buy_ta=ta
                await asyncio.sleep(0.5)

            if best_buy:
                amount=min(data["auto_size"],usdt*0.95)
                if amount>=5:
                    await do_auto_trade_direct(uid,data["chat_id"],best_buy,"BUY",amount,best_buy_ta,ctx)
                    await asyncio.sleep(2)

async def dca_job(ctx):
    now=time.time()
    for uid,data in list(USER_DATA.items()):
        for bot in data.get("dca_bots",[]):
            if not bot.get("active"): continue
            if now<bot["next_run"]: continue
            order=place_order(bot["symbol"],"BUY",bot["amount"])
            bot["next_run"]=now+bot["interval_h"]*3600
            bot["runs"]+=1; bot["total_invested"]+=bot["amount"]
            chat_id=bot.get("chat_id")
            if chat_id and order["ok"]:
                mt=" _(Демо)_" if order.get("mock") else ""
                try:
                    await ctx.bot.send_message(chat_id,
                        f"🔄 *DCA Покупка*{mt}\n\n"
                        f"*{bot['symbol']}* `{order['qty']:.6f}` @ `${order['price']:,.4f}`\n"
                        f"Сумма: `${order['total']:.2f}` | Раз: `{bot['runs']}`",
                        parse_mode=ParseMode.MARKDOWN)
                except: pass

async def daily_report_job(ctx):
    """Send daily PnL report at configured hour."""
    now=datetime.utcnow()
    if now.hour!=DAILY_REPORT_HOUR: return
    for uid,data in list(USER_DATA.items()):
        if not data.get("daily_report"): continue
        chat_id=data.get("chat_id")
        if not chat_id: continue
        try:
            bals=get_real_balance(); bals.pop("_error",None); bals.pop("_mock",None)
            usdt=bals.get("USDT",0); total=usdt
            lines=["📊 *Ежедневный отчёт*\n",
                   f"📅 {now.strftime('%d.%m.%Y')}\n"]
            for asset,qty in bals.items():
                if asset=="USDT": continue
                t=get_price(asset)
                if "error" not in t: v=qty*t["price"]; total+=v; lines.append(f"• *{asset}*: `${v:.2f}`")
            lines.append(f"\n💎 *Итого:* `${total:.2f}`")
            fg=fear_greed()
            lines.append(f"{fg['emoji']} Страх/Жадность: `{fg['value']}` — {fg['label']}")
            # Best/worst coins
            prices=get_all_prices()
            sorted_p=sorted(prices.items(),key=lambda x:x[1].get("change",0),reverse=True)
            if sorted_p:
                best=sorted_p[0]; worst=sorted_p[-1]
                lines.append(f"\n🟢 Лучший: *{best[0].replace('USDT','')}* `{best[1].get('change',0):+.2f}%`")
                lines.append(f"🔴 Худший: *{worst[0].replace('USDT','')}* `{worst[1].get('change',0):+.2f}%`")
            await ctx.bot.send_message(chat_id,"\n".join(lines),
                                        parse_mode=ParseMode.MARKDOWN,reply_markup=back())
        except Exception as e: log.error(f"Daily report: {e}")

async def change_alert_job(ctx):
    """Check % change alerts efficiently using bulk price fetch."""
    try:
        prices=get_all_prices()
        for uid,data in list(USER_DATA.items()):
            triggered,remaining=[],[]
            for alert in data.get("alerts",[]):
                if alert["condition"]!="change": remaining.append(alert); continue
                s=alert["symbol"]
                if s in prices:
                    chg=abs(prices[s].get("change",0))
                    if chg>=alert["price"]: triggered.append((alert,prices[s]["price"],prices[s]))
                    else: remaining.append(alert)
                else: remaining.append(alert)
            data["alerts"]=remaining
            for alert,cur,ticker in triggered:
                chat_id=alert.get("chat_id")
                if chat_id:
                    try:
                        await ctx.bot.send_message(chat_id,
                            f"📊 *% АЛЕРТ!*\n\n"
                            f"*{alert['symbol']}* изменился на `{ticker.get('change',0):+.2f}%`\n"
                            f"Текущая: `${cur:,.4f}`",
                            parse_mode=ParseMode.MARKDOWN)
                    except: pass
    except Exception as e: log.error(f"Change alert: {e}")

# ── HEALTH SERVER ─────────────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK v8.0")
    def log_message(self,*a): pass

def health():
    HTTPServer(("0.0.0.0",PORT),H).serve_forever()

# ── MAIN ──────────────────────────────────────────────────────────
async def main():
    if TELEGRAM_TOKEN=="YOUR_TOKEN":
        print("Set TELEGRAM_TOKEN!"); return
    Thread(target=health,daemon=True).start()
    app=Application.builder().token(TELEGRAM_TOKEN).build()
    for cmd,fn in [
        ("start",cmd_start),("help",cmd_help),
        ("buy",cmd_buy),("sell",cmd_sell),
        ("trail",cmd_trail),("dca",cmd_dca),("grid",cmd_grid),
        ("auto",cmd_auto),("scan",cmd_scan),
        ("price",cmd_price),("portfolio",cmd_portfolio),
        ("pnl",cmd_pnl),("orders",cmd_orders),("balance",cmd_balance),
        ("analysis",cmd_analysis),("alert",cmd_alert),("fg",cmd_fg),
        ("news",cmd_news),("convert",cmd_convert),("settings",cmd_settings)]:
        app.add_handler(CommandHandler(cmd,fn))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_handler))
    app.job_queue.run_repeating(alerts_job,      interval=60,  first=15)
    app.job_queue.run_repeating(auto_job,         interval=600, first=120)
    app.job_queue.run_repeating(dca_job,          interval=300, first=90)
    app.job_queue.run_repeating(daily_report_job, interval=3600,first=60)
    app.job_queue.run_repeating(change_alert_job, interval=300, first=60)
    log.info("🚀 Bot v8.0 started!")
    async with app:
        await app.initialize(); await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__=="__main__":
    asyncio.run(main())
