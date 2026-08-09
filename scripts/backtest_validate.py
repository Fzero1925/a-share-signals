import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data_manager import DataManager
from core.indicators import add_all_indicators
from core.portfolio_backtest import PortfolioBacktester

RESULTS_FILE = "reports/backtest_results.json"
REPORT_DIR = "reports"
POOL_CACHE = os.path.join(REPORT_DIR, "pool_codes.json")


def fetch_codes_from_pool(dm: DataManager, max_count: int) -> list[str]:
    if os.path.exists(POOL_CACHE):
        with open(POOL_CACHE, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if len(cached) >= max_count:
            return cached[:max_count]
    from core.screener import build_candidate_pool

    pool = build_candidate_pool(min_amount=1e9, max_pages=5, max_candidates=max_count)
    codes = pool["code"].tolist() if not pool.empty else []
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(POOL_CACHE, "w", encoding="utf-8") as f:
        json.dump(codes, f, ensure_ascii=False)
    return codes


def _fetch_one(dm: DataManager, code: str):
    try:
        df = dm.get_daily(code, "20230601", None, use_cache=True)
        if df.empty or len(df) < 100:
            return None
        return code, add_all_indicators(df)
    except Exception:
        return None


def fetch_history(dm: DataManager, codes: list[str], workers: int = 8) -> dict:
    stock_data = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_fetch_one, dm, code): code for code in codes}
        for fut in as_completed(futures):
            res = fut.result()
            if res is not None:
                code, df = res
                stock_data[code] = df
    return stock_data


def fetch_benchmark(dm: DataManager) -> pd.DataFrame:
    try:
        df = dm.get_index_daily("sh000300", "20220601")
        return df[["date", "close"]].reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=["date", "close"])


def run_backtest(stock_data: dict, top_n: int, min_score: float, start_date: str) -> dict:
    bt = PortfolioBacktester(initial_capital=100000, top_n=top_n, min_score=min_score)
    return bt.run(stock_data, start_date=start_date)


def result_to_row(period_label: str, top_n: int, min_score: float, result: dict) -> dict:
    m = result["metrics"]
    return {
        "时段": period_label,
        "top_n": top_n,
        "min_score": min_score,
        "总收益": round(m.get("total_return", 0), 6),
        "年化": round(m.get("annual_return", 0), 6),
        "最大回撤": round(m.get("max_drawdown", 0), 6),
        "夏普": round(m.get("sharpe", 0), 4),
        "胜率": round(m.get("win_rate", 0), 6),
        "交易次数": m.get("trades", 0),
    }


def main() -> int:
    dm = DataManager()
    os.makedirs(REPORT_DIR, exist_ok=True)

    print("1/4 获取候选池(成交额>10亿)...")
    codes = fetch_codes_from_pool(dm, max_count=100)
    print(f"   候选池: {len(codes)} 只")
    if not codes:
        print("候选池为空", file=sys.stderr)
        return 1

    print("2/4 拉取历史K线(2022-06至今)...")
    stock_data = fetch_history(dm, codes)
    print(f"   可用: {len(stock_data)} 只")

    print("3/4 拉取沪深300基准...")
    benchmark = fetch_benchmark(dm)
    print(f"   基准: {len(benchmark)} 行")

    periods = [
        ("2023下半年", "20230701"),
        ("2024全年", "20240101"),
        ("2025至今", "20250101"),
        ("2023至今", "20230701"),
    ]

    param_grid = [
        (3, 0.2),
        (3, 0.3),
        (5, 0.2),
        (5, 0.3),
        (8, 0.2),
        (8, 0.3),
    ]

    results = []
    best = None
    best_key = None
    for period_label, start in periods:
        print(f"\n--- {period_label} ---")
        for top_n, min_score in param_grid:
            t0 = time.time()
            result = run_backtest(stock_data, top_n, min_score, start)
            row = result_to_row(period_label, top_n, min_score, result)
            results.append(row)
            print(
                f"   top_n={top_n} min_score={min_score}: 总收益={row['总收益']:.2%} "
                f"回撤={row['最大回撤']:.2%} 夏普={row['夏普']:.2f} "
                f"交易{row['交易次数']}次 ({time.time()-t0:.0f}s)"
            )
            if best is None or row["总收益"] > best["总收益"]:
                best = row
                best_key = f"{period_label}_top{top_n}_ms{min_score}"
                best["_equity"] = result["equity_curve"].to_dict("records")

    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"rows": [r for r in results if "_equity" not in r], "best_key": best_key},
            f,
            ensure_ascii=False,
            indent=2,
        )

    summary = pd.DataFrame([r for r in results if "_equity" not in r])
    summary.to_csv(os.path.join(REPORT_DIR, "backtest_summary.csv"), index=False, encoding="utf-8-sig")
    print("\n\n=== 参数对比汇总 ===")
    pd.set_option("display.width", 150)
    print(summary.to_string(index=False))

    print(f"\n4/4 最优参数: {best_key}, 生成 quantstats 报告...")
    if best and best.get("_equity"):
        try:
            import quantstats as qs

            eq = pd.DataFrame(best["_equity"]).set_index("date")["equity"]
            eq.index = pd.to_datetime(eq.index)
            benchmark_close = benchmark.set_index("date")["close"]
            benchmark_close.index = pd.to_datetime(benchmark_close.index)
            common_start = max(eq.index.min(), benchmark_close.index.min())
            eq = eq[eq.index >= common_start]
            benchmark_close = benchmark_close[benchmark_close.index >= common_start]
            out = os.path.join(REPORT_DIR, f"quantstats_{best_key}.html")
            qs.reports.html(
                eq,
                benchmark=benchmark_close,
                output=out,
                title=f"每日动量策略 {best_key}",
            )
            print(f"   报告: {out}")
        except Exception as e:
            print(f"   quantstats 报告失败: {e}", file=sys.stderr)

    print("\n完成。结果见 reports/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
