import json
import os
from datetime import datetime

class TradeTracker:
    def __init__(self, history_file="trades_history.json"):
        self.history_file = history_file
        self.trades = self.load_trades()
        # Active trades are ones that haven't hit TP or SL yet
        self.active_trades = []
        
    def load_trades(self):
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r') as f:
                return json.load(f)
        return []

    def save_trades(self):
        with open(self.history_file, 'w') as f:
            json.dump(self.trades, f, indent=4)

    def add_trade(self, pair, direction, entry_price, tp, sl):
        if direction == "NEUTRAL":
            return
            
        trade = {
            "id": f"{pair}_{int(datetime.now().timestamp())}",
            "pair": pair,
            "direction": direction,
            "entry_price": entry_price,
            "tp": tp,
            "sl": sl,
            "status": "OPEN", # OPEN, WIN, LOSS
            "close_price": None,
            "time_opened": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "time_closed": None
        }
        self.trades.append(trade)
        self.active_trades.append(trade)
        self.save_trades()

    def update_prices(self, pair, current_price):
        """
        Checks active trades against the current price to see if they hit TP or SL
        Returns the number of trades just closed in this update.
        """
        closed_count = 0
        still_active = []
        
        for trade in self.active_trades:
            if trade['pair'] != pair:
                still_active.append(trade)
                continue
                
            hit_tp = False
            hit_sl = False
            
            if trade['direction'] == "UP":
                if current_price >= trade['tp']: hit_tp = True
                if current_price <= trade['sl']: hit_sl = True
            elif trade['direction'] == "DOWN":
                if current_price <= trade['tp']: hit_tp = True
                if current_price >= trade['sl']: hit_sl = True
                
            if hit_tp:
                trade['status'] = "WIN"
                trade['close_price'] = current_price
                trade['time_closed'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                closed_count += 1
            elif hit_sl:
                trade['status'] = "LOSS"
                trade['close_price'] = current_price
                trade['time_closed'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                closed_count += 1
            else:
                still_active.append(trade)
                
        if closed_count > 0:
            self.active_trades = still_active
            self.save_trades()
            
        return closed_count

    def get_stats(self, pair=None):
        wins = 0
        losses = 0
        
        for t in self.trades:
            if pair and t['pair'] != pair:
                continue
            if t['status'] == "WIN": wins += 1
            if t['status'] == "LOSS": losses += 1
            
        total_closed = wins + losses
        win_rate = (wins / total_closed * 100) if total_closed > 0 else 0
        loss_rate = (losses / total_closed * 100) if total_closed > 0 else 0
        
        return {
            "total_predictions": len([t for t in self.trades if (not pair or t['pair'] == pair)]),
            "total_closed": total_closed,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 2),
            "loss_rate": round(loss_rate, 2)
        }
