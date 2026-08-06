import numpy as np
import pandas as pd


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["ma5"] = df["close"].rolling(5).mean()
    df["ma10"] = df["close"].rolling(10).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()

    df["ema5"] = df["close"].ewm(span=5, adjust=False).mean()
    df["ema10"] = df["close"].ewm(span=10, adjust=False).mean()
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()

    macd = _macd(df["close"], 12, 26, 9)
    df["macd_dif"] = macd["dif"]
    df["macd_dea"] = macd["dea"]
    df["macd_hist"] = macd["hist"]

    df["rsi14"] = _rsi(df["close"], 14)

    boll = _bollinger(df["close"], 20, 2.0)
    df["boll_upper"] = boll["upper"]
    df["boll_mid"] = boll["mid"]
    df["boll_lower"] = boll["lower"]

    df["adx14"] = _adx(df["high"], df["low"], df["close"], 14)

    df["atr14"] = _atr(df["high"], df["low"], df["close"], 14)

    df["vol_ma5"] = df["volume"].rolling(5).mean()
    df["vol_ma20"] = df["volume"].rolling(20).mean()

    df["high_20"] = df["close"].rolling(20).max()
    df["low_10"] = df["close"].rolling(10).min()

    return df


def _macd(close: pd.Series, fast: int, slow: int, signal: int) -> pd.DataFrame:
    dif = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = (dif - dea) * 2
    return pd.DataFrame({"dif": dif, "dea": dea, "hist": hist})


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return rsi.fillna(50)


def _bollinger(close: pd.Series, period: int, num_std: float) -> pd.DataFrame:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    return pd.DataFrame(
        {
            "upper": mid + num_std * std,
            "mid": mid,
            "lower": mid - num_std * std,
        }
    )


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    return _true_range(high, low, close).ewm(alpha=1 / period, adjust=False).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=high.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=high.index,
    )

    atr = _atr(high, low, close, period)

    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx
