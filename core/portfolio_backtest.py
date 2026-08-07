import numpy as np
import pandas as pd

from core.backtest_engine import calc_cost, can_buy, can_sell
from strategies.daily_momentum import DailyMomentumStrategy


class PortfolioBacktester:
    def __init__(self, initial_capital: float = 100000.0, top_n: int = 5):
        self.initial_capital = initial_capital
        self.top_n = top_n
        self.strategy = DailyMomentumStrategy({"top_n": top_n})

    def run(self, stock_data: dict, start_date: str = "20250101") -> dict:
        """
        组合回测：每日收盘后打分选top N，次日开盘调仓
        stock_data: {code: df}，df含OHLCV
        规则：
        - T+1：当日买入次日才能卖
        - 涨跌停：涨停买不进、跌停卖不出
        - 手续费：买卖双向
        - 等权分配
        """
        common_dates = None
        for df in stock_data.values():
            dates = set(df["date"])
            common_dates = dates if common_dates is None else common_dates & dates
        if not common_dates:
            return {"equity_curve": pd.DataFrame(), "trades": pd.DataFrame(), "metrics": {}}
        dates = sorted(common_dates)
        start = pd.to_datetime(start_date)
        dates = [d for d in dates if d >= start]

        cash = self.initial_capital
        positions: dict[str, dict] = {}
        equity_rows = []
        trades = []

        for i, date in enumerate(dates):
            day_slice = {code: df[df["date"] == date] for code, df in stock_data.items()}
            available = {code: row for code, row in day_slice.items() if not row.empty}
            if not available:
                continue

            prices = {code: float(row.iloc[0]["close"]) for code, row in available.items()}
            pre_closes = {}
            for code, row in available.items():
                df = stock_data[code]
                idx = df.index[df["date"] == date][0]
                if idx > 0:
                    pre_closes[code] = float(df.iloc[idx - 1]["close"])
                else:
                    pre_closes[code] = float(row.iloc[0]["open"])

            if i > 0:
                scored = self.strategy.score_universe(
                    {code: stock_data[code][stock_data[code]["date"] <= date] for code in stock_data}
                )
                target = scored.head(self.top_n).index.tolist() if not scored.empty else []

                for code in list(positions.keys()):
                    if code not in target and code in prices:
                        pos = positions[code]
                        if date > pos["entry_date"] and can_sell(prices[code], pre_closes[code], code):
                            cost = calc_cost(prices[code], pos["shares"], "sell")
                            proceeds = prices[code] * pos["shares"] - cost
                            cash += proceeds
                            pnl = proceeds - pos["shares"] * pos["entry_price"] - calc_cost(pos["entry_price"], pos["shares"], "buy")
                            pnl_pct = pnl / (pos["shares"] * pos["entry_price"])
                            trades.append({
                                "date": date.strftime("%Y-%m-%d"),
                                "code": code,
                                "action": "SELL",
                                "price": prices[code],
                                "shares": pos["shares"],
                                "pnl": round(pnl, 2),
                                "pnl_pct": round(pnl_pct, 6),
                            })
                            del positions[code]

                budget = cash / max(len(target), 1)
                for code in target:
                    if code in positions or code not in prices:
                        continue
                    price = prices[code]
                    if not can_buy(price, pre_closes[code], code):
                        continue
                    shares = int(budget / price / 100) * 100
                    if shares < 100:
                        continue
                    cost = calc_cost(price, shares, "buy")
                    total = price * shares + cost
                    if cash < total:
                        continue
                    cash -= total
                    positions[code] = {"shares": shares, "entry_price": price, "entry_date": date}
                    trades.append({
                        "date": date.strftime("%Y-%m-%d"),
                        "code": code,
                        "action": "BUY",
                        "price": price,
                        "shares": shares,
                        "pnl": 0.0,
                        "pnl_pct": 0.0,
                    })

            market_value = sum(
                pos["shares"] * prices[code] for code, pos in positions.items() if code in prices
            )
            total_equity = cash + market_value
            equity_rows.append({"date": date, "equity": total_equity})

        equity_curve = pd.DataFrame(equity_rows)
        trades_df = pd.DataFrame(trades)
        metrics = self._calc_metrics(equity_curve, trades_df)
        return {"equity_curve": equity_curve, "trades": trades_df, "metrics": metrics}

    @staticmethod
    def _calc_metrics(equity_curve: pd.DataFrame, trades: pd.DataFrame) -> dict:
        if equity_curve.empty:
            return {"total_return": 0, "annual_return": 0, "max_drawdown": 0, "sharpe": 0, "win_rate": 0, "trades": 0}
        initial = equity_curve["equity"].iloc[0]
        final = equity_curve["equity"].iloc[-1]
        total_return = final / initial - 1
        years = len(equity_curve) / 252
        annual = (1 + total_return) ** (1 / years) - 1 if years > 0 and total_return > -1 else -1

        drawdown = equity_curve["equity"] / equity_curve["equity"].cummax() - 1
        max_dd = drawdown.min()

        returns = equity_curve["equity"].pct_change().dropna()
        std = returns.std()
        sharpe = returns.mean() / std * np.sqrt(252) if std and std > 0 else 0

        sells = trades[trades["action"] == "SELL"] if not trades.empty else pd.DataFrame()
        total = len(sells)
        win_rate = (sells["pnl"] > 0).mean() if total > 0 else 0
        return {
            "total_return": total_return,
            "annual_return": annual,
            "max_drawdown": float(max_dd),
            "sharpe": float(sharpe),
            "win_rate": float(win_rate),
            "trades": total,
        }
