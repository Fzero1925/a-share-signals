import pandas as pd

from core.indicators import add_all_indicators
from core.strategy_base import BaseStrategy


class TrendFollowStrategy(BaseStrategy):
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in ["ema5", "ema20", "adx14"]:
            if col not in df.columns:
                df = add_all_indicators(df)
                break

        df["signal"] = 0
        df["position"] = 0

        fast = self.get_param("fast_ema", 5)
        slow = self.get_param("slow_ema", 20)
        adx_threshold = self.get_param("adx_threshold", 25)
        stop_loss = self.get_param("stop_loss_pct", 0.05)
        trailing_stop = self.get_param("trailing_stop_pct", 0.03)
        take_profit = self.get_param("take_profit_pct", 0.15)

        position = 0
        entry_price = 0.0
        highest_since_entry = 0.0

        ema_fast = df["ema5"].to_numpy()
        ema_slow = df["ema20"].to_numpy()
        adx = df["adx14"].to_numpy()
        close = df["close"].to_numpy()
        start = max(fast, slow, 14)

        for i in range(len(df)):
            if i < start:
                df.at[df.index[i], "position"] = position
                continue
            cross_up = ema_fast[i] > ema_slow[i] and ema_fast[i - 1] <= ema_slow[i - 1]
            cross_down = ema_fast[i] < ema_slow[i]

            if position == 0:
                if cross_up and adx[i] >= adx_threshold and close[i] > ema_slow[i]:
                    df.at[df.index[i], "signal"] = 1
                    position = 1
                    entry_price = close[i]
                    highest_since_entry = close[i]
            else:
                highest_since_entry = max(highest_since_entry, close[i])
                hit_stop = close[i] <= entry_price * (1 - stop_loss)
                hit_trailing = close[i] <= highest_since_entry * (1 - trailing_stop)
                hit_profit = close[i] >= entry_price * (1 + take_profit)
                if cross_down or hit_stop or hit_trailing or hit_profit:
                    df.at[df.index[i], "signal"] = -1
                    position = 0

            df.at[df.index[i], "position"] = position

        return df

    @staticmethod
    def get_default_params() -> dict:
        return {
            "fast_ema": 5,
            "slow_ema": 20,
            "adx_period": 14,
            "adx_threshold": 25,
            "stop_loss_pct": 0.05,
            "trailing_stop_pct": 0.03,
            "take_profit_pct": 0.15,
        }
