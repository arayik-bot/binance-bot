from binance_client import BinanceClient
import json
import config
import os

class Portfolio:
    def __init__(self):
        self.client = BinanceClient()
        self.data_file = config.DATA_FILE
        self._init_data()
    
    def _init_data(self):
        if not os.path.exists(self.data_file):
            with open(self.data_file, 'w') as f:
                json.dump({"daily_pnl": 0, "total_trades": 0}, f)
    
    def get_balance_summary(self):
        balances = self.client.get_account_balance()
        total_usd = 0
        assets = []
        for asset, amount in balances.items():
            if amount['free'] + amount['locked'] > 0:
                price = self.client.get_symbol_price(f"{asset}USDT") if asset != "USDT" else 1
                value = (amount['free'] + amount['locked']) * price
                total_usd += value
                assets.append({"asset": asset, "amount": amount['free']+amount['locked'], "value_usd": value})
        return {"total_usd": total_usd, "assets": assets}
    
    def update_pnl(self, realized_pnl):
        with open(self.data_file, 'r') as f:
            data = json.load(f)
        data['daily_pnl'] += realized_pnl
        data['total_trades'] += 1
        # Check daily loss limit
        if data['daily_pnl'] < -config.DAILY_LOSS_LIMIT_USD:
            from bot import stop_trading
            stop_trading()
        with open(self.data_file, 'w') as f:
            json.dump(data, f)
        return data['daily_pnl']
