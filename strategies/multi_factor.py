import numpy as np
import pandas as pd

from core.indicators import add_all_indicators
from core.strategy_base import MultiStockStrategy


class MultiFactorStrategy(MultiStockStrategy):
    FACTOR_WEIGHTS = {
        "momentum_20d": 0.25,
        "volatility_20d": 0.15,
        "volume_ratio_5d": 0.20,
        "trend_strength": 0.25,
        "rsi_score": 0.15,
    }

    def generate_signals(self, stock_data: dict) -> dict:
        top_n = self.get_param("top_n", 5)
        rebalance_freq = self.get_param("rebalance_freq", "weekly")
        rebalance_days = 5 if rebalance_freq == "weekly" else 20

        results = {}
        for code, df in stock_data.items():
            df = df.copy()
            for col in ["ma60", "rsi14"]:
                if col not in df.columns:
                    df = add_all_indicators(df)
                    break
            df["signal"] = 0
            df["position"] = 0
            results[code] = df

        common_dates = set(results[list(results.keys())[0]]["date"])
        for df in results.values():
            common_dates &= set(df["date"])
        dates = sorted(common_dates)

        prev_top: list[str] = []
        day_count = 0

        for date in dates:
            day_count += 1
            rebalance_today = day_count % rebalance_days == 0 or day_count == 1
            if not rebalance_today:
                for code, df in results.items():
                    prev_pos = df.loc[df["date"] == date, "position"]
                    idx = df.index[df["date"] == date][0]
                    if prev_pos.empty:
                        df.at[idx, "position"] = 0
                    else:
                        df.at[idx, "position"] = prev_pos.iloc[0]
                continue

            scores = {}
            for code, df in results.items():
                row_idx = df.index[df["date"] == date]
                if row_idx.empty or row_idx[0] < 60:
                    scores[code] = np.nan
                    continue
                row = df.iloc[row_idx[0]]
                momentum = row["close"] / df.loc[row_idx[0] - 20, "close"] - 1 if row_idx[0] >= 20 else np.nan
                returns = df["close"].pct_change().iloc[max(0, row_idx[0] - 20): row_idx[0] + 1]
                volatility = returns.std() if len(returns) >= 2 else np.nan
                vol_5 = df["volume"].iloc[max(0, row_idx[0] - 5): row_idx[0] + 1]
                volume_ratio = df["volume"].iloc[row_idx[0]] / vol_5.mean() if len(vol_5) >= 2 else np.nan
                trend_strength = (row["close"] - row["ma60"]) / row["ma60"] if row["ma60"] == row["ma60"] else np.nan
                rsi_score = (row["rsi14"] - 50) / 50 if row["rsi14"] == row["rsi14"] else np.nan
                scores[code] = {
                    "momentum_20d": momentum,
                    "volatility_20d": -volatility,
                    "volume_ratio_5d": volume_ratio,
                    "trend_strength": trend_strength,
                    "rsi_score": rsi_score,
                }

            cleaned = {c: s for c, s in scores.items() if s == s and all(v == v for v in s.values())}
            if not cleaned:
                continue

            factor_df = pd.DataFrame(cleaned).T
            ranked = factor_df.rank(pct=True)
            total_score = sum(
                self.FACTOR_WEIGHTS[k] * ranked[k] for k in self.FACTOR_WEIGHTS
            )
            ranked["score"] = total_score
            ranked = ranked.sort_values("score", ascending=False)
            new_top = ranked.index[:top_n].tolist()

            for code, df in results.items():
                idx = df.index[df["date"] == date][0]
                if code in new_top:
                    if code not in prev_top:
                        df.at[idx, "signal"] = 1
                    df.at[idx, "position"] = 1
                else:
                    if code in prev_top:
                        df.at[idx, "signal"] = -1
                    df.at[idx, "position"] = 0

            prev_top = new_top

        return results

    @staticmethod
    def get_default_params() -> dict:
        return {
            "top_n": 5,
            "momentum_period": 20,
            "volume_period": 5,
            "rebalance_freq": "weekly",
        }
