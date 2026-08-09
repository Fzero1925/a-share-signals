import numpy as np
import pandas as pd

from core.backtest_engine import calc_cost, can_buy, can_sell
from strategies.daily_momentum import DailyMomentumStrategy


class PortfolioBacktester:
    def __init__(self, initial_capital: float = 100000.0, top_n: int = 5, min_score: float = 0.3):
        self.initial_capital = initial_capital
        self.top_n = top_n
        self.min_score = min_score
        self.strategy = DailyMomentumStrategy({"top_n": top_n})

    def run(self, stock_data: dict, start_date: str = "20250101") -> dict:
        """
        组合回测：每日收盘后打分选top N，次日调仓
        stock_data: {code: df}，df含OHLCV
        规则：T+1、涨跌停、手续费、等权分配
        """
        prepared = {}
        for code, df in stock_data.items():
            df = df.reset_index(drop=True)
            if len(df) < 60:
                continue
            dates = pd.to_datetime(df["date"]).to_numpy()
            close = df["close"].to_numpy(dtype=float)
            prepared[code] = {
                "dates": dates,
                "close": close,
                "ma60": df["ma60"].to_numpy(dtype=float) if "ma60" in df.columns else np.full(len(df), np.nan),
                "rsi14": df["rsi14"].to_numpy(dtype=float) if "rsi14" in df.columns else np.full(len(df), np.nan),
                "vol_ma20": df["vol_ma20"].to_numpy(dtype=float) if "vol_ma20" in df.columns else np.full(len(df), np.nan),
                "volume": df["volume"].to_numpy(dtype=float),
            }
        if not prepared:
            return {"equity_curve": pd.DataFrame(), "trades": pd.DataFrame(), "metrics": {}}

        all_dates = set()
        for p in prepared.values():
            all_dates.update(p["dates"])
        trading_dates = sorted(all_dates)
        start = pd.Timestamp(start_date)
        common_dates = [d for d in trading_dates if d >= start]
        if not common_dates:
            return {"equity_curve": pd.DataFrame(), "trades": pd.DataFrame(), "metrics": {}}

        date_to_idx = {}
        for code, p in prepared.items():
            p["index_map"] = {d: i for i, d in enumerate(p["dates"])}
            date_to_idx[code] = p["index_map"]

        def fmt(d) -> str:
            return pd.Timestamp(d).strftime("%Y-%m-%d")

        cash = self.initial_capital
        positions: dict[str, dict] = {}
        equity_rows = []
        trades = []
        last_prices: dict[str, float] = {}

        n_days = len(common_dates)
        for i, date in enumerate(common_dates):
            prices = {}
            pre_closes = {}
            for code, p in prepared.items():
                idx = p["index_map"].get(date)
                if idx is None:
                    continue
                prices[code] = float(p["close"][idx])
                pre_closes[code] = float(p["close"][idx - 1]) if idx > 0 else float(p["close"][idx])

            if not prices:
                continue

            if i > 0:
                target = self._score_at(prepared, date_to_idx, date, i, n_days)

                for code in list(positions.keys()):
                    if code not in target and code in prices:
                        pos = positions[code]
                        if date > pd.Timestamp(pos["entry_date"]) and can_sell(prices[code], pre_closes[code], code):
                            cost = calc_cost(prices[code], pos["shares"], "sell")
                            proceeds = prices[code] * pos["shares"] - cost
                            cash += proceeds
                            pnl = proceeds - pos["shares"] * pos["entry_price"] - calc_cost(
                                pos["entry_price"], pos["shares"], "buy"
                            )
                            pnl_pct = pnl / (pos["shares"] * pos["entry_price"])
                            trades.append({
                                "date": fmt(date),
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
                        "date": fmt(date),
                        "code": code,
                        "action": "BUY",
                        "price": price,
                        "shares": shares,
                        "pnl": 0.0,
                        "pnl_pct": 0.0,
                    })

            market_value = 0.0
            for code, pos in positions.items():
                if code in prices:
                    market_value += pos["shares"] * prices[code]
                elif code in last_prices:
                    market_value += pos["shares"] * last_prices[code]
            equity_rows.append({"date": date, "equity": cash + market_value})

            for code in prices:
                last_prices[code] = prices[code]

        equity_curve = pd.DataFrame(equity_rows)
        trades_df = pd.DataFrame(trades)
        metrics = self._calc_metrics(equity_curve, trades_df)
        return {"equity_curve": equity_curve, "trades": trades_df, "metrics": metrics}

    def _score_at(self, prepared: dict, date_to_idx: dict, date, i: int, n_days: int) -> list:
        rows = []
        for code, p in prepared.items():
            idx = p["index_map"].get(date)
            if idx is None or idx < 20:
                continue
            close = p["close"][idx]
            if not np.isfinite(close) or close <= 0:
                continue
            c_5 = p["close"][idx - 5] if idx >= 5 else np.nan
            c_20 = p["close"][idx - 20] if idx >= 20 else np.nan
            vol_now = p["volume"][idx]
            vol_ma = p["vol_ma20"][idx]
            ma60 = p["ma60"][idx]
            rsi = p["rsi14"][idx]

            momentum_20 = (close / c_20 - 1) if np.isfinite(c_20) and c_20 > 0 else np.nan
            momentum_5 = (close / c_5 - 1) if np.isfinite(c_5) and c_5 > 0 else np.nan
            vol_ratio = (vol_now / vol_ma) if np.isfinite(vol_ma) and vol_ma > 0 and np.isfinite(vol_now) else np.nan
            trend = ((close - ma60) / ma60) if np.isfinite(ma60) and ma60 > 0 else np.nan
            rsi_score = ((rsi - 50) / 50) if np.isfinite(rsi) else np.nan

            rows.append({
                "code": code,
                "momentum_20d": momentum_20,
                "momentum_5d": momentum_5,
                "volume_ratio": vol_ratio,
                "trend_strength": trend,
                "rsi_score": rsi_score,
            })

        if not rows:
            return []
        factor_df = pd.DataFrame(rows).set_index("code")
        rank_df = factor_df[
            ["momentum_20d", "momentum_5d", "volume_ratio", "trend_strength", "rsi_score"]
        ].rank(pct=True)
        w = DailyMomentumStrategy.FACTOR_WEIGHTS
        score = sum(w[k] * rank_df[k] for k in w)
        result = score.sort_values(ascending=False)
        result = result[result >= self.min_score]
        return result.head(self.top_n).index.tolist()

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
