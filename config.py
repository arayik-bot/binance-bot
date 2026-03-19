import os

class Config:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
    BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")

    _raw = os.getenv("ALLOWED_USERS", "")
    ALLOWED_USERS = [int(x.strip()) for x in _raw.split(",") if x.strip().isdigit()]

    DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "BTCUSDT")
    MAX_TRADE_SIZE_USD = float(os.getenv("MAX_TRADE_SIZE_USD", "100"))
    DAILY_LOSS_LIMIT_USD = float(os.getenv("DAILY_LOSS_LIMIT_USD", "50"))
    READ_ONLY = os.getenv("READ_ONLY", "false").lower() == "true"
    FUTURES_LEVERAGE = int(os.getenv("FUTURES_LEVERAGE", "1"))

    RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
    RSI_OVERSOLD = float(os.getenv("RSI_OVERSOLD", "30"))
    RSI_OVERBOUGHT = float(os.getenv("RSI_OVERBOUGHT", "70"))
    MA_FAST = int(os.getenv("MA_FAST", "9"))
    MA_SLOW = int(os.getenv("MA_SLOW", "21"))

    ALERT_CHECK_INTERVAL = int(os.getenv("ALERT_CHECK_INTERVAL", "60"))
    STRATEGY_CHECK_INTERVAL = int(os.getenv("STRATEGY_CHECK_INTERVAL", "300"))
