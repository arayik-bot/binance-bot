import os
from dotenv import load_dotenv

load_dotenv()

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Անվտանգություն
ALLOWED_USER_IDS = list(map(int, os.getenv("ALLOWED_USER_IDS", "").split(",")))
MAX_TRADE_SIZE_USD = float(os.getenv("MAX_TRADE_SIZE_USD", "500"))
DAILY_LOSS_LIMIT_USD = float(os.getenv("DAILY_LOSS_LIMIT_USD", "1000"))
READ_ONLY_MODE = os.getenv("READ_ONLY_MODE", "False").lower() == "true"

# Trading parameters
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MA_SHORT = 7
MA_LONG = 25

# Auto-trade confirmation timeout (seconds)
CONFIRM_TIMEOUT = 30

# Database (simple JSON for demo)
DATA_FILE = "bot_data.json"
