import json
import os
from datetime import datetime
from typing import Optional

from config.settings import INITIAL_CAPITAL, PORTFOLIO_DIR
from core.backtest_engine import calc_cost


class PortfolioManager:
    def __init__(self, initial_capital: float = INITIAL_CAPITAL):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: dict[str, dict] = {}
        self.trade_history: list[dict] = []
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.updated_at = self.created_at

    def buy(self, stock_code: str, price: float, shares: int, date: str, reason: str = "") -> bool:
        if shares <= 0 or shares % 100 != 0:
            return False
        if stock_code in self.positions:
            return False
        cost = calc_cost(price, shares, "buy")
        total = price * shares + cost
        if self.cash < total:
            return False
        self.cash -= total
        self.positions[stock_code] = {
            "shares": shares,
            "entry_price": price,
            "entry_date": date,
            "reason": reason,
        }
        self.trade_history.append(
            {
                "date": date,
                "code": stock_code,
                "action": "BUY",
                "price": price,
                "shares": shares,
                "cost": round(cost, 2),
                "reason": reason,
            }
        )
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return True

    def sell(self, stock_code: str, price: float, date: str, reason: str = "") -> bool:
        if stock_code not in self.positions:
            return False
        pos = self.positions[stock_code]
        shares = pos["shares"]
        cost = calc_cost(price, shares, "sell")
        proceeds = price * shares - cost
        self.cash += proceeds
        pnl = proceeds - shares * pos["entry_price"]
        buy_cost = calc_cost(pos["entry_price"], shares, "buy")
        pnl_pct = pnl / (shares * pos["entry_price"] + buy_cost)
        self.trade_history.append(
            {
                "date": date,
                "code": stock_code,
                "action": "SELL",
                "price": price,
                "shares": shares,
                "cost": round(cost, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 6),
                "reason": reason,
            }
        )
        del self.positions[stock_code]
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return True

    def get_position(self, stock_code: str) -> Optional[dict]:
        return self.positions.get(stock_code)

    def get_all_positions(self) -> dict:
        return self.positions

    def get_total_equity(self, current_prices: dict) -> float:
        market_value = sum(
            pos["shares"] * current_prices[code]
            for code, pos in self.positions.items()
            if code in current_prices
        )
        return self.cash + market_value

    def get_position_value(self, current_prices: dict) -> float:
        return sum(
            pos["shares"] * current_prices[code]
            for code, pos in self.positions.items()
            if code in current_prices
        )

    def get_performance(self, current_prices: dict) -> dict:
        total_equity = self.get_total_equity(current_prices)
        total_return = total_equity / self.initial_capital - 1
        total_profit = total_equity - self.initial_capital
        sell_trades = [t for t in self.trade_history if t["action"] == "SELL"]
        win_trades = sum(1 for t in sell_trades if t.get("pnl", 0) > 0)
        loss_trades = sum(1 for t in sell_trades if t.get("pnl", 0) <= 0)
        return {
            "total_return": total_return,
            "total_profit": total_profit,
            "win_trades": win_trades,
            "loss_trades": loss_trades,
            "total_equity": total_equity,
            "current_positions": len(self.positions),
        }

    def get_trade_history(self) -> list:
        return self.trade_history

    def save_state(self, filepath: Optional[str] = None) -> None:
        if filepath is None:
            os.makedirs(PORTFOLIO_DIR, exist_ok=True)
            filepath = os.path.join(PORTFOLIO_DIR, "paper_account.json")
        state = {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "positions": self.positions,
            "trade_history": self.trade_history,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def load_state(self, filepath: Optional[str] = None) -> bool:
        if filepath is None:
            filepath = os.path.join(PORTFOLIO_DIR, "paper_account.json")
        if not os.path.exists(filepath):
            return False
        with open(filepath, "r", encoding="utf-8") as f:
            state = json.load(f)
        self.initial_capital = state["initial_capital"]
        self.cash = state["cash"]
        self.created_at = state.get("created_at", "")
        self.updated_at = state.get("updated_at", "")
        self.positions = state.get("positions", {})
        self.trade_history = state.get("trade_history", [])
        return True
