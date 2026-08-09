import json
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import PORTFOLIO_DIR, SIGNALS_DIR
from core.calendar import is_trading_day
from core.data_manager import DataManager
from core.indicators import add_all_indicators
from core.portfolio_engine import PortfolioEngine
from core.screener import build_candidate_pool
from strategies.daily_momentum import DailyMomentumStrategy

PORTFOLIO_FILE = os.path.join(SIGNALS_DIR, "portfolio_state.json")
LOOKBACK_DAYS = 90
TOP_N = 5
INITIAL_CAPITAL = 100000.0


def fetch_history_batch(dm: DataManager, codes: list[str]) -> dict:
    stock_data = {}
    for code in codes:
        try:
            df = dm.get_daily(code, use_cache=False)
            if df.empty or len(df) < 60:
                continue
            df = add_all_indicators(df)
            stock_data[code] = df
        except Exception:
            continue
    return stock_data


def main() -> int:
    if not is_trading_day():
        print("今日非交易日（周末或节假日），跳过组合调仓")
        return 0

    dm = DataManager()

    pool = build_candidate_pool(min_amount=3e8, max_pages=5, max_candidates=300)
    if pool.empty:
        print("候选池为空，退出", file=sys.stderr)
        return 1
    codes = pool["code"].tolist()
    names = dict(zip(pool["code"], pool["name"]))

    stock_data = fetch_history_batch(dm, codes)
    if not stock_data:
        print("无可用K线数据，退出", file=sys.stderr)
        return 1

    strategy = DailyMomentumStrategy({"top_n": TOP_N})
    selected = strategy.select_top(stock_data, top_n=TOP_N)

    target_positions = {code: INITIAL_CAPITAL / TOP_N for code in selected}

    latest_date = None
    prices = {}
    pre_closes = {}
    for code, df in stock_data.items():
        if len(df) < 2:
            continue
        prices[code] = float(df["close"].iloc[-1])
        pre_closes[code] = float(df["close"].iloc[-2])
        d = df["date"].iloc[-1]
        if latest_date is None or d > latest_date:
            latest_date = d

    if latest_date is None:
        print("无最新日期，退出", file=sys.stderr)
        return 1

    date_str = pd.to_datetime(latest_date).strftime("%Y-%m-%d")

    engine = PortfolioEngine(INITIAL_CAPITAL)
    if os.path.exists(PORTFOLIO_FILE):
        engine.load_state(PORTFOLIO_FILE)

    if engine.equity_history and engine.equity_history[-1].get("date") == date_str:
        print(f"今日({date_str})已执行过调仓，跳过")
        return 0

    report = engine.execute_rebalance(
        date=date_str,
        target_positions=target_positions,
        prices=prices,
        pre_closes=pre_closes,
        names=names,
    )

    engine.save_state(PORTFOLIO_FILE)

    perf = engine.get_performance(prices)

    os.makedirs(SIGNALS_DIR, exist_ok=True)
    output = {
        "date": date_str,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "strategy": "DailyMomentum",
        "pool_size": len(pool),
        "selected": [
            {
                "code": c,
                "name": names.get(c, c),
                "close": prices.get(c),
                "target_amount": target_positions.get(c),
            }
            for c in selected
        ],
        "rebalance": report,
        "performance": perf,
        "equity_history": engine.equity_history,
        "positions": [
            {
                "code": code,
                "name": pos.get("name", code),
                "shares": pos["shares"],
                "entry_price": pos["entry_price"],
                "entry_date": pos["entry_date"],
                "current_price": prices.get(code, pos["entry_price"]),
            }
            for code, pos in engine.positions.items()
        ],
    }

    with open(os.path.join(SIGNALS_DIR, "portfolio.json"), "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
