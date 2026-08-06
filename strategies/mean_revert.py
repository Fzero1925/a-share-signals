import pandas as pd

from core.indicators import add_all_indicators
from core.strategy_base import BaseStrategy


class MeanRevertStrategy(BaseStrategy):
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in ["boll_upper", "boll_mid", "boll_lower", "rsi14"]:
            if col not in df.columns:
                df = add_all_indicators(df)
                break

        df["signal"] = 0
        df["position"] = 0

        rsi_oversold = self.get_param("rsi_oversold", 35)
        rsi_overbought = self.get_param("rsi_overbought", 65)
        stop_loss = self.get_param("stop_loss_pct", 0.03)
        take_profit = self.get_param("take_profit_pct", 0.05)
        max_hold = self.get_param("max_hold_days", 7)

        position = 0
        entry_price = 0.0
        hold_days = 0

        close = df["close"].to_numpy()
        upper = df["boll_upper"].to_numpy()
        mid = df["boll_mid"].to_numpy()
        lower = df["boll_lower"].to_numpy()
        rsi = df["rsi14"].to_numpy()
        bb_width = (upper - lower) / mid

        for i in range(len(df)):
            if i < 20:
                df.at[df.index[i], "position"] = position
                continue

            if position == 0:
                hit_lower = close[i] <= lower[i] * 1.01
                oversold = rsi[i] < rsi_oversold
                wide_enough = bb_width[i] > 0.05
                up_day = close[i] > close[i - 1]
                if hit_lower and oversold and wide_enough and up_day:
                    df.at[df.index[i], "signal"] = 1
                    position = 1
                    entry_price = close[i]
                    hold_days = 0
            else:
                hold_days += 1
                back_to_mid = close[i] >= mid[i]
                overbought = rsi[i] > rsi_overbought
                hit_stop = close[i] <= entry_price * (1 - stop_loss)
                hit_profit = close[i] >= entry_price * (1 + take_profit)
                time_out = hold_days >= max_hold
                if back_to_mid or overbought or hit_stop or hit_profit or time_out:
                    df.at[df.index[i], "signal"] = -1
                    position = 0

            df.at[df.index[i], "position"] = position

        return df

    @staticmethod
    def get_default_params() -> dict:
        return {
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_period": 14,
            "rsi_oversold": 35,
            "rsi_overbought": 65,
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.05,
            "max_hold_days": 7,
        }
