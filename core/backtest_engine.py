from typing import Optional

import numpy as np
import pandas as pd

from config.settings import (
    COMMISSION,
    INITIAL_CAPITAL,
    LIMIT_UP_PCT_GEM,
    LIMIT_UP_PCT_MAIN,
    MIN_COMMISSION,
    RISK_FREE_RATE,
    STAMP_TAX,
    TRANSFER_FEE,
)


def calc_cost(price: float, shares: int, action: str) -> float:
    amount = price * shares
    commission = max(amount * COMMISSION, MIN_COMMISSION)
    transfer = amount * TRANSFER_FEE
    stamp = amount * STAMP_TAX if action == "sell" else 0.0
    return commission + transfer + stamp


def can_buy(close: float, pre_close: float, stock_code: str) -> bool:
    limit_pct = LIMIT_UP_PCT_GEM if stock_code.startswith(("300", "688")) else LIMIT_UP_PCT_MAIN
    limit_up = pre_close * (1 + limit_pct)
    return close < limit_up


def can_sell(close: float, pre_close: float, stock_code: str) -> bool:
    limit_pct = LIMIT_UP_PCT_GEM if stock_code.startswith(("300", "688")) else LIMIT_UP_PCT_MAIN
    limit_down = pre_close * (1 - limit_pct)
    return close > limit_down


class BacktestEngine:
    def __init__(self, initial_capital: float = INITIAL_CAPITAL):
        self.initial_capital = initial_capital

    def run(
        self,
        df: pd.DataFrame,
        stock_code: str = "000001",
        position_pct: float = 0.3,
    ) -> dict:
        if "signal" not in df.columns:
            raise ValueError("df 缺少 signal 列，请先运行策略 generate_signals")

        df = df.copy().reset_index(drop=True)
        cash = self.initial_capital
        holding_shares = 0
        entry_price = 0.0
        entry_date = None
        highest_since_entry = 0.0
        trades = []
        equity_rows = []

        close_arr = df["close"].to_numpy()
        signal_arr = df["signal"].to_numpy()
        dates = df["date"].tolist()

        for i in range(len(df)):
            date = dates[i]
            close = float(close_arr[i])
            pre_close = float(close_arr[i - 1]) if i > 0 else close
            signal = int(signal_arr[i])

            market_value = holding_shares * close
            total_equity = cash + market_value

            if signal == 1 and holding_shares == 0:
                if can_buy(close, pre_close, stock_code):
                    buy_amount = total_equity * position_pct
                    shares = int(buy_amount / close / 100) * 100
                    if shares >= 100:
                        cost = calc_cost(close, shares, "buy")
                        if cash >= close * shares + cost:
                            cash -= close * shares + cost
                            holding_shares = shares
                            entry_price = close
                            entry_date = date
                            highest_since_entry = close
                            trades.append(
                                {
                                    "date": date,
                                    "action": "BUY",
                                    "price": close,
                                    "shares": shares,
                                    "cost": cost,
                                    "pnl": 0.0,
                                    "pnl_pct": 0.0,
                                }
                            )

            elif signal == -1 and holding_shares > 0:
                if date > entry_date and can_sell(close, pre_close, stock_code):
                    sell_amount = close * holding_shares
                    cost = calc_cost(close, holding_shares, "sell")
                    pnl = sell_amount - cost - holding_shares * entry_price
                    buy_cost = calc_cost(entry_price, holding_shares, "buy")
                    total_cost = holding_shares * entry_price + buy_cost
                    pnl_pct = pnl / total_cost
                    cash += sell_amount - cost
                    trades.append(
                        {
                            "date": date,
                            "action": "SELL",
                            "price": close,
                            "shares": holding_shares,
                            "cost": cost,
                            "pnl": round(pnl, 2),
                            "pnl_pct": round(pnl_pct, 6),
                        }
                    )
                    holding_shares = 0
                    entry_price = 0.0
                    entry_date = None

            if holding_shares > 0 and close > highest_since_entry:
                highest_since_entry = close

            market_value = holding_shares * close
            total_equity = cash + market_value
            equity_rows.append(
                {
                    "date": date,
                    "equity": total_equity,
                    "cash": cash,
                    "position_value": market_value,
                }
            )

        equity_curve = pd.DataFrame(equity_rows)
        equity_curve["drawdown"] = (equity_curve["equity"] / equity_curve["equity"].cummax() - 1).fillna(0)
        trades_df = pd.DataFrame(trades)

        metrics = self.calc_metrics(equity_curve, trades_df)

        return {
            "trades": trades_df,
            "equity_curve": equity_curve,
            "metrics": metrics,
            "df": df,
        }

    @staticmethod
    def calc_metrics(equity_curve: pd.DataFrame, trades: Optional[pd.DataFrame]) -> dict:
        if equity_curve is None or equity_curve.empty:
            return {
                "total_return": 0.0,
                "annual_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "win_rate": 0.0,
                "profit_loss_ratio": 0.0,
                "total_trades": 0,
            }
        initial = equity_curve["equity"].iloc[0]
        final = equity_curve["equity"].iloc[-1]
        total_return = final / initial - 1

        trading_days = len(equity_curve)
        years = trading_days / 252
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0

        max_drawdown = equity_curve["drawdown"].min()

        returns = equity_curve["equity"].pct_change().dropna()
        rf_daily = RISK_FREE_RATE / 252
        excess = returns - rf_daily
        std = float(excess.std()) if len(excess) > 1 else 0.0
        sharpe = np.sqrt(252) * float(excess.mean()) / std if std > 1e-10 else 0.0

        win_rate = 0.0
        profit_loss_ratio = 0.0
        total_trades = 0
        if trades is not None and not trades.empty:
            sells = trades[trades["action"] == "SELL"]
            total_trades = len(sells)
            if len(sells) > 0:
                wins = sells[sells["pnl"] > 0]
                losses = sells[sells["pnl"] <= 0]
                win_rate = len(wins) / len(sells)
                avg_win = wins["pnl_pct"].mean() if len(wins) > 0 else 0.0
                avg_loss = abs(losses["pnl_pct"].mean()) if len(losses) > 0 else 0.0
                profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

        return {
            "total_return": total_return,
            "annual_return": annual_return,
            "max_drawdown": float(max_drawdown),
            "sharpe_ratio": sharpe,
            "win_rate": win_rate,
            "profit_loss_ratio": profit_loss_ratio,
            "total_trades": total_trades,
        }
