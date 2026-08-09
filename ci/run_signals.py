import json
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import MONITOR_STOCKS, SIGNALS_DIR
from core.calendar import is_trading_day
from core.data_manager import DataManager
from core.indicators import add_all_indicators
from strategies.momentum import MomentumStrategy
from strategies.trend_follow import TrendFollowStrategy


def load_monitor_stocks(path: str = MONITOR_STOCKS) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"监控股票池文件不存在: {path}")
    return pd.read_csv(path, dtype={"code": str})


def run_strategy_signals(dm: DataManager, code: str) -> dict:
    df = dm.get_daily(code, "20240101", None, use_cache=False)
    if df.empty or len(df) < 60:
        return None
    df = add_all_indicators(df)

    result = {"code": code, "strategies": []}

    for strat_cls in [TrendFollowStrategy, MomentumStrategy]:
        strategy = strat_cls()
        df_sig = strategy.generate_signals(df)
        latest = df_sig.iloc[-1]
        prev = df_sig.iloc[-2]
        action = "HOLD"
        reason = ""
        if latest["signal"] == 1:
            action = "BUY"
            reason = "触发买入信号"
        elif latest["signal"] == -1:
            action = "SELL"
            reason = "触发卖出信号"
        elif latest["position"] == 1:
            action = "HOLD"
            reason = "持仓中"
        result["strategies"].append(
            {
                "strategy": strategy.name,
                "action": action,
                "reason": reason,
                "close": round(float(latest["close"]), 3),
                "pct_change": round(float(latest["close"] / prev["close"] - 1) * 100, 2),
                "rsi14": round(float(latest["rsi14"]), 1) if latest["rsi14"] == latest["rsi14"] else None,
                "adx14": round(float(latest["adx14"]), 1) if latest["adx14"] == latest["adx14"] else None,
            }
        )

    return result


def fetch_market_summary(dm: DataManager) -> dict:
    summary = {}
    try:
        sh = dm.get_index_daily("sh000001", "20240101")
        sz = dm.get_index_daily("sz399001", "20240101")
        if not sh.empty:
            summary["shanghai"] = {
                "close": round(float(sh["close"].iloc[-1]), 2),
                "pct_change": round(float(sh["close"].iloc[-1] / sh["close"].iloc[-2] - 1) * 100, 2),
            }
        if not sz.empty:
            summary["shenzhen"] = {
                "close": round(float(sz["close"].iloc[-1]), 2),
                "pct_change": round(float(sz["close"].iloc[-1] / sz["close"].iloc[-2] - 1) * 100, 2),
            }
    except Exception as e:
        summary["error"] = str(e)
    return summary


def main() -> int:
    if not is_trading_day():
        print("今日非交易日（周末或节假日），跳过信号生成")
        return 0

    dm = DataManager()
    os.makedirs(SIGNALS_DIR, exist_ok=True)

    stocks = load_monitor_stocks()
    signals = []
    failures = []

    for _, row in stocks.iterrows():
        code = str(row["code"]).zfill(6)
        name = row["name"]
        try:
            sig = run_strategy_signals(dm, code)
            if sig:
                sig["name"] = name
                signals.append(sig)
        except Exception as e:
            failures.append({"code": code, "name": name, "error": str(e)})

    output = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market_summary": fetch_market_summary(dm),
        "signals": signals,
        "failures": failures,
    }

    os.makedirs(SIGNALS_DIR, exist_ok=True)
    with open(os.path.join(SIGNALS_DIR, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    date_file = os.path.join(SIGNALS_DIR, f"{datetime.now().strftime('%Y%m%d')}.json")
    with open(date_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(json.dumps(output, ensure_ascii=False, indent=2))

    if failures:
        print(f"\n警告: {len(failures)} 只股票获取失败", file=sys.stderr)
        for f in failures:
            print(f"  {f['code']} {f['name']}: {f['error']}", file=sys.stderr)

    return 0 if len(signals) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
