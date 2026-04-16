from binance.client import Client
from config import Config
import logging

logger = logging.getLogger(__name__)
_client = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(Config.BINANCE_API_KEY, Config.BINANCE_SECRET_KEY)
    return _client


def safe_symbol(symbol: str) -> str:
    symbol = symbol.upper().replace("/", "").replace("-", "")
    if not any(symbol.endswith(q) for q in ["USDT", "BTC", "ETH", "BNB", "BUSD"]):
        symbol += "USDT"
    return symbol


def get_price(symbol: str) -> float:
    ticker = get_client().get_symbol_ticker(symbol=safe_symbol(symbol))
    return float(ticker['price'])


def get_24h_stats(symbol: str) -> dict:
    return get_client().get_ticker(symbol=safe_symbol(symbol))


def get_order_book(symbol: str, limit: int = 5) -> dict:
    return get_client().get_order_book(symbol=safe_symbol(symbol), limit=limit)


def get_klines(symbol: str, interval: str = "1h", limit: int = 100) -> list:
    return get_client().get_klines(symbol=safe_symbol(symbol), interval=interval, limit=limit)


def get_spot_balance() -> list:
    account = get_client().get_account()
    return [b for b in account['balances'] if float(b['free']) > 0 or float(b['locked']) > 0]


def get_futures_balance() -> list:
    return get_client().futures_account()['assets']


def get_futures_positions() -> list:
    positions = get_client().futures_position_information()
    return [p for p in positions if float(p['positionAmt']) != 0]


def get_open_orders(symbol: str = None) -> list:
    if symbol:
        return get_client().get_open_orders(symbol=safe_symbol(symbol))
    return get_client().get_open_orders()


def get_trade_history(symbol: str, limit: int = 10) -> list:
    return get_client().get_my_trades(symbol=safe_symbol(symbol), limit=limit)


def get_top_gainers(limit: int = 10) -> list:
    tickers = get_client().get_ticker()
    usdt = [t for t in tickers if t['symbol'].endswith('USDT')]
    return sorted(usdt, key=lambda x: float(x['priceChangePercent']), reverse=True)[:limit]


def get_top_losers(limit: int = 10) -> list:
    tickers = get_client().get_ticker()
    usdt = [t for t in tickers if t['symbol'].endswith('USDT')]
    return sorted(usdt, key=lambda x: float(x['priceChangePercent']))[:limit]


def get_futures_funding_rate(symbol: str) -> dict:
    rates = get_client().futures_funding_rate(symbol=safe_symbol(symbol), limit=1)
    return rates[0] if rates else {}


def place_spot_order(symbol: str, side: str, quantity: float) -> dict:
    if Config.READ_ONLY:
        raise Exception("🛡 Read-Only mode ակտիվ է։ Trading disabled.")
    return get_client().order_market(symbol=safe_symbol(symbol), side=side, quantity=quantity)


def place_futures_order(symbol: str, side: str, quantity: float) -> dict:
    if Config.READ_ONLY:
        raise Exception("🛡 Read-Only mode ակտիվ է։ Trading disabled.")
    return get_client().futures_create_order(
        symbol=safe_symbol(symbol), side=side, type="MARKET", quantity=quantity
    )


def get_symbol_info(symbol: str) -> dict:
    return get_client().get_symbol_info(safe_symbol(symbol))
