import json
import os
from datetime import datetime
from typing import Optional

import pandas as pd

from config.settings import PORTFOLIO_DIR
from core.backtest_engine import calc_cost, can_buy, can_sell


class PortfolioEngine:
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: dict[str, dict] = {}
        self.trade_history: list[dict] = []
        self.equity_history: list[dict] = []
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.updated_at = self.created_at

    def execute_rebalance(
        self,
        date: str,
        target_positions: dict[str, float],
        prices: dict[str, float],
        pre_closes: dict[str, float],
        names: Optional[dict[str, str]] = None,
    ) -> dict:
        """
        执行每日调仓（收盘价成交）
        target_positions: {code: 目标金额}
        prices: {code: 当前收盘价}
        pre_closes: {code: 昨收}
        names: {code: 名称}
        返回: {sold: [...], bought: [...], blocked: [...], skipped: [...]}
        """
        names = names or {}
        report = {"sold": [], "bought": [], "blocked": [], "skipped": []}

        sell_codes = [c for c in self.positions if c not in target_positions]
        for code in sell_codes:
            pos = self.positions[code]
            price = prices.get(code)
            pre_close = pre_closes.get(code)
            if price is None or pre_close is None:
                report["blocked"].append({"code": code, "reason": "无行情"})
                continue
            if not can_sell(price, pre_close, code):
                report["blocked"].append({"code": code, "reason": "跌停卖不出"})
                continue
            self._sell(code, price, date, "调仓卖出")
            report["sold"].append({"code": code, "price": price})

        for code, target_amount in target_positions.items():
            price = prices.get(code)
            pre_close = pre_closes.get(code)
            if price is None or pre_close is None:
                report["skipped"].append({"code": code, "reason": "无行情"})
                continue
            if not can_buy(price, pre_close, code):
                report["blocked"].append({"code": code, "reason": "涨停买不进"})
                continue
            if code in self.positions:
                continue
            shares = int(target_amount / price / 100) * 100
            if shares < 100:
                report["skipped"].append({"code": code, "reason": "资金不足1手"})
                continue
            cost = calc_cost(price, shares, "buy")
            total = price * shares + cost
            if self.cash < total:
                report["skipped"].append({"code": code, "reason": "现金不足"})
                continue
            self._buy(code, shares, price, date, names.get(code, code), "调仓买入")
            report["bought"].append({"code": code, "name": names.get(code, code), "shares": shares, "price": price})

        total_equity = self.get_total_equity(prices)
        self.equity_history.append(
            {
                "date": date,
                "equity": round(total_equity, 2),
                "cash": round(self.cash, 2),
                "positions": len(self.positions),
            }
        )
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return report

    def record_equity(self, date: str, prices: dict) -> None:
        total_equity = self.get_total_equity(prices)
        if self.equity_history and self.equity_history[-1]["date"] == date:
            self.equity_history[-1] = {
                "date": date,
                "equity": round(total_equity, 2),
                "cash": round(self.cash, 2),
                "positions": len(self.positions),
            }
        else:
            self.equity_history.append(
                {
                    "date": date,
                    "equity": round(total_equity, 2),
                    "cash": round(self.cash, 2),
                    "positions": len(self.positions),
                }
            )

    def _buy(self, code: str, shares: int, price: float, date: str, name: str, reason: str) -> None:
        cost = calc_cost(price, shares, "buy")
        self.cash -= price * shares + cost
        self.positions[code] = {
            "shares": shares,
            "entry_price": price,
            "entry_date": date,
            "reason": reason,
            "name": name,
        }
        self.trade_history.append(
            {
                "date": date,
                "code": code,
                "name": name,
                "action": "BUY",
                "price": price,
                "shares": shares,
                "cost": round(cost, 2),
                "reason": reason,
            }
        )

    def _sell(self, code: str, price: float, date: str, reason: str) -> None:
        pos = self.positions[code]
        shares = pos["shares"]
        cost = calc_cost(price, shares, "sell")
        proceeds = price * shares - cost
        self.cash += proceeds
        buy_cost = calc_cost(pos["entry_price"], shares, "buy")
        pnl = proceeds - shares * pos["entry_price"] - buy_cost
        pnl_pct = pnl / (shares * pos["entry_price"] + buy_cost)
        self.trade_history.append(
            {
                "date": date,
                "code": code,
                "name": pos.get("name", code),
                "action": "SELL",
                "price": price,
                "shares": shares,
                "cost": round(cost, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 6),
                "reason": reason,
            }
        )
        del self.positions[code]

    def get_position_value(self, prices: dict) -> float:
        return sum(
            pos["shares"] * prices[code]
            for code, pos in self.positions.items()
            if code in prices
        )

    def get_total_equity(self, prices: dict) -> float:
        return self.cash + self.get_position_value(prices)

    def get_performance(self, prices: dict) -> dict:
        total_equity = self.get_total_equity(prices)
        sells = [t for t in self.trade_history if t["action"] == "SELL"]
        wins = sum(1 for t in sells if t.get("pnl", 0) > 0)
        return {
            "total_equity": round(total_equity, 2),
            "total_return": total_equity / self.initial_capital - 1,
            "total_profit": total_equity - self.initial_capital,
            "cash": round(self.cash, 2),
            "position_value": round(self.get_position_value(prices), 2),
            "positions": len(self.positions),
            "win_trades": wins,
            "loss_trades": len(sells) - wins,
            "total_trades": len(sells),
        }

    def get_equity_curve(self) -> pd.DataFrame:
        if not self.equity_history:
            return pd.DataFrame(columns=["date", "equity", "cash", "positions"])
        return pd.DataFrame(self.equity_history)

    def get_trade_history(self) -> pd.DataFrame:
        if not self.trade_history:
            return pd.DataFrame(
                columns=["date", "code", "name", "action", "price", "shares", "cost", "pnl", "pnl_pct", "reason"]
            )
        return pd.DataFrame(self.trade_history)

    def get_latest_price_map(self, prices: dict) -> dict:
        result = {}
        for code, pos in self.positions.items():
            result[code] = prices.get(code, pos["entry_price"])
        return result

    def save_state(self, filepath: Optional[str] = None) -> None:
        if filepath is None:
            os.makedirs(PORTFOLIO_DIR, exist_ok=True)
            filepath = os.path.join(PORTFOLIO_DIR, "paper_account.json")
        else:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
        state = {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "positions": self.positions,
            "trade_history": self.trade_history,
            "equity_history": self.equity_history,
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
        self.equity_history = state.get("equity_history", [])
        return True
