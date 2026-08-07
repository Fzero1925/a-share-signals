import numpy as np
import pandas as pd

from core.indicators import add_all_indicators
from core.strategy_base import MultiStockStrategy


class DailyMomentumStrategy(MultiStockStrategy):
    FACTOR_WEIGHTS = {
        "momentum_20d": 0.30,
        "momentum_5d": 0.20,
        "volume_ratio": 0.15,
        "trend_strength": 0.20,
        "rsi_score": 0.15,
    }

    def score_universe(self, stock_data: dict) -> pd.DataFrame:
        rows = []
        for code, df in stock_data.items():
            if df is None or df.empty or len(df) < 60:
                continue
            df = df.copy()
            for col in ["ma60", "rsi14", "vol_ma20"]:
                if col not in df.columns:
                    df = add_all_indicators(df)
                    break
            last = df.iloc[-1]
            close = last["close"]
            if close != close or close <= 0:
                continue

            def safe_get(series_name: str, offset: int = 0):
                if len(df) > offset:
                    return df.iloc[-1 - offset][series_name]
                return np.nan

            c_now = close
            c_5 = safe_get("close", 5)
            c_20 = safe_get("close", 20)
            vol_now = last.get("volume", np.nan)
            vol_ma = last.get("vol_ma20", np.nan)
            ma60 = last.get("ma60", np.nan)
            rsi = last.get("rsi14", np.nan)

            momentum_20 = (c_now / c_20 - 1) if c_20 == c_20 and c_20 > 0 else np.nan
            momentum_5 = (c_now / c_5 - 1) if c_5 == c_5 and c_5 > 0 else np.nan
            vol_ratio = (vol_now / vol_ma) if (vol_ma == vol_ma and vol_ma > 0 and vol_now == vol_now) else np.nan
            trend = ((c_now - ma60) / ma60) if (ma60 == ma60 and ma60 > 0) else np.nan
            rsi_score = ((rsi - 50) / 50) if (rsi == rsi) else np.nan

            rows.append(
                {
                    "code": code,
                    "momentum_20d": momentum_20,
                    "momentum_5d": momentum_5,
                    "volume_ratio": vol_ratio,
                    "trend_strength": trend,
                    "rsi_score": rsi_score,
                    "close": c_now,
                }
            )

        if not rows:
            return pd.DataFrame(columns=["code", "score", "close"])

        factor_df = pd.DataFrame(rows).set_index("code")
        rank_df = factor_df[
            ["momentum_20d", "momentum_5d", "volume_ratio", "trend_strength", "rsi_score"]
        ].rank(pct=True)
        score = sum(self.FACTOR_WEIGHTS[k] * rank_df[k] for k in self.FACTOR_WEIGHTS)
        result = pd.DataFrame({"score": score, "close": factor_df["close"]})
        return result.sort_values("score", ascending=False)

    def select_top(self, stock_data: dict, top_n: int = 5, min_score: float = 0.3) -> list[str]:
        scored = self.score_universe(stock_data)
        if scored.empty:
            return []
        scored = scored[scored["score"] >= min_score]
        return scored.head(top_n).index.tolist()

    def generate_signals(self, stock_data: dict) -> dict:
        top_n = self.get_param("top_n", 5)
        scored = self.score_universe(stock_data)
        top = scored.head(top_n).index.tolist() if not scored.empty else []
        result = {}
        for code, df in stock_data.items():
            df = df.copy()
            df["signal"] = 0
            df["position"] = 1 if code in top else 0
            if code in top:
                df.loc[df.index[-1], "signal"] = 1
            else:
                df.loc[df.index[-1], "signal"] = -1
            result[code] = df
        return result

    @staticmethod
    def get_default_params() -> dict:
        return {
            "top_n": 5,
            "momentum_20d": 0.30,
            "momentum_5d": 0.20,
            "volume_ratio": 0.15,
            "trend_strength": 0.20,
            "rsi_score": 0.15,
            "min_amount": 3e8,
            "max_candidates": 300,
        }
