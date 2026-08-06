from core.backtest_engine import BacktestEngine
from core.data_manager import DataManager
from core.indicators import add_all_indicators
from strategies.mean_revert import MeanRevertStrategy
from strategies.momentum import MomentumStrategy
from strategies.trend_follow import TrendFollowStrategy

dm = DataManager()

for code in ["000001", "600519", "300750"]:
    df = dm.get_daily(code, "20210101", "20241231")
    df = add_all_indicators(df)
    print(f"== {code} 数据{len(df)}行 ==")
    for Strat in [TrendFollowStrategy, MeanRevertStrategy, MomentumStrategy]:
        s = Strat()
        df_sig = s.generate_signals(df.copy())
        engine = BacktestEngine(1000000)
        result = engine.run(df_sig, code)
        m = result["metrics"]
        print(
            f"  {s.__class__.__name__}: 总收益={m['total_return']:.2%} "
            f"夏普={m['sharpe_ratio']:.2f} 胜率={m['win_rate']:.2%} "
            f"回撤={m['max_drawdown']:.2%} 交易{m['total_trades']}次"
        )
