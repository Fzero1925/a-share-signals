import pandas as pd

from core.indicators import add_all_indicators
from core.strategy_base import BaseStrategy


class MomentumStrategy(BaseStrategy):
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in ["high_20", "low_10", "vol_ma20", "ma60", "ma10"]:
            if col not in df.columns:
                df = add_all_indicators(df)
                break

        df["signal"] = 0
        df["position"] = 0

        volume_ratio_threshold = self.get_param("volume_ratio", 1.5)
        stop_loss = self.get_param("stop_loss_pct", 0.05)
        trailing_stop = self.get_param("trailing_stop_pct", 0.04)

        position = 0
        entry_price = 0.0
        highest_since_entry = 0.0

        close = df["close"].to_numpy()
        high_20 = df["high_20"].to_numpy()
        low_10 = df["low_10"].to_numpy()
        vol = df["volume"].to_numpy()
        vol_ma20 = df["vol_ma20"].to_numpy()
        ma60 = df["ma60"].to_numpy()
        ma10 = df["ma10"].to_numpy()
        vol_ratio = vol / vol_ma20

        for i in range(len(df)):
            if i < 20:
                df.at[df.index[i], "position"] = position
                continue

            if position == 0:
                breakout = close[i] > high_20[i - 1]
                volume_ok = vol_ratio[i] >= volume_ratio_threshold
                trend_up = close[i] > ma60[i]
                if breakout and volume_ok and trend_up:
                    df.at[df.index[i], "signal"] = 1
                    position = 1
                    entry_price = close[i]
                    highest_since_entry = close[i]
            else:
                highest_since_entry = max(highest_since_entry, close[i])
                below_ma10 = close[i] < ma10[i]
                below_low = close[i] <= low_10[i - 1]
                hit_stop = close[i] <= entry_price * (1 - stop_loss)
                hit_trailing = close[i] <= highest_since_entry * (1 - trailing_stop)
                if below_ma10 or below_low or hit_stop or hit_trailing:
                    df.at[df.index[i], "signal"] = -1
                    position = 0

            df.at[df.index[i], "position"] = position

        return df

    @staticmethod
    def get_default_params() -> dict:
        return {
            "lookback_high": 20,
            "lookback_low": 10,
            "volume_ma": 20,
            "volume_ratio": 1.5,
            "stop_loss_pct": 0.05,
            "trailing_stop_pct": 0.04,
        }
