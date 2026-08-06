import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core.backtest_engine import BacktestEngine
from core.data_manager import DataFetchError, DataManager
from core.indicators import add_all_indicators
from core.strategy_engine import STRATEGY_REGISTRY, get_strategy

PARAM_META = {
    "fast_ema": (2, 50, 1),
    "slow_ema": (5, 120, 1),
    "adx_period": (5, 40, 1),
    "adx_threshold": (10, 50, 1),
    "stop_loss_pct": (0.01, 0.15, 0.005),
    "trailing_stop_pct": (0.01, 0.10, 0.005),
    "take_profit_pct": (0.05, 0.50, 0.01),
    "bb_period": (5, 60, 1),
    "bb_std": (1.0, 3.5, 0.1),
    "rsi_period": (5, 30, 1),
    "rsi_oversold": (10, 45, 1),
    "rsi_overbought": (55, 90, 1),
    "max_hold_days": (1, 30, 1),
    "lookback_high": (10, 60, 1),
    "lookback_low": (5, 30, 1),
    "volume_ma": (10, 60, 1),
    "volume_ratio": (1.0, 3.0, 0.1),
    "top_n": (2, 20, 1),
    "rebalance_freq": None,
}


@st.cache_data(ttl=3600, show_spinner=False)
def load_data(code: str, start: str, end: str):
    dm = DataManager()
    return dm.get_daily(code, start, end)


def param_controls(strategy_name: str, defaults: dict) -> dict:
    params = {}
    for key, value in defaults.items():
        meta = PARAM_META.get(key)
        if meta is None:
            params[key] = st.text_input(f"参数 {key}", value=str(value))
            continue
        if key == "rebalance_freq":
            params[key] = st.selectbox("调仓频率", ["weekly", "monthly"], index=0 if value == "weekly" else 1)
            continue
        min_v, max_v, step = meta
        is_float = isinstance(value, float)
        if is_float:
            params[key] = st.slider(f"{key}", float(min_v), float(max_v), float(value), float(step))
        else:
            params[key] = st.slider(f"{key}", int(min_v), int(max_v), int(value), int(step))
    return params


def build_result_charts(result: dict, df: pd.DataFrame, stock_code: str):
    df = df.copy()
    buys = df[df["signal"] == 1]
    sells = df[df["signal"] == -1]

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.55, 0.25, 0.20],
        vertical_spacing=0.03,
    )

    fig.add_trace(
        go.Candlestick(
            x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            name="K线",
            increasing_line_color="red",
            decreasing_line_color="green",
        ),
        row=1, col=1,
    )
    for col, color in [("ma10", "orange"), ("ma20", "blue"), ("ma60", "purple")]:
        if col in df.columns:
            fig.add_trace(
                go.Scatter(x=df["date"], y=df[col], name=col.upper(), line=dict(color=color, width=1)),
                row=1, col=1,
            )
    fig.add_trace(
        go.Scatter(
            x=buys["date"], y=buys["low"] * 0.98,
            mode="markers", name="买入",
            marker=dict(symbol="triangle-up", size=12, color="lime"),
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=sells["date"], y=sells["high"] * 1.02,
            mode="markers", name="卖出",
            marker=dict(symbol="triangle-down", size=12, color="red"),
        ),
        row=1, col=1,
    )

    colors = ["red" if c >= o else "green" for c, o in zip(df["close"], df["open"])]
    fig.add_trace(
        go.Bar(x=df["date"], y=df["volume"], name="成交量", marker_color=colors),
        row=2, col=1,
    )

    ec = result["equity_curve"]
    fig.add_trace(
        go.Scatter(x=ec["date"], y=ec["equity"], name="策略权益", line=dict(color="blue", width=2)),
        row=3, col=1,
    )
    fig.add_trace(
        go.Scatter(x=ec["date"], y=ec["drawdown"] * 100, name="回撤%", line=dict(color="red", width=1), fill="tozeroy"),
        row=3, col=1,
        secondary_y=False,
    )

    fig.update_layout(
        height=800,
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=40, b=10),
    )
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    fig.update_yaxes(title_text="权益/回撤%", row=3, col=1)
    return fig


def show():
    st.title("📈 策略回测")

    col1, col2, col3, col4 = st.columns([1.2, 1, 1, 1])
    with col1:
        strategy_name = st.selectbox("选择策略", list(STRATEGY_REGISTRY.keys()))
    with col2:
        code_input = st.text_input("股票代码", value="000001")
    with col3:
        start_date = st.text_input("开始日期", value="20210101")
    with col4:
        end_date = st.text_input("结束日期", value="20251231")

    with st.expander("⚙️ 策略参数"):
        defaults = STRATEGY_REGISTRY[strategy_name].get_default_params()
        params = param_controls(strategy_name, defaults)
        col_a, col_b, col_c = st.columns(3)
        initial_capital = col_a.number_input("初始资金", min_value=10000, value=100000, step=10000)
        position_pct = col_b.slider("单票仓位比例", 0.05, 1.0, 0.3, 0.05)
        col_c.write("")
        col_c.write("")
        run_btn = col_c.button("🚀 运行回测", type="primary")

    if run_btn:
        try:
            df = load_data(code_input.strip().zfill(6), start_date, end_date)
            if df.empty:
                st.warning("所选日期范围内无数据")
                return
            df = add_all_indicators(df)

            strategy = get_strategy(strategy_name, params)
            df_signal = strategy.generate_signals(df)

            engine = BacktestEngine(float(initial_capital))
            result = engine.run(df_signal, code_input.strip().zfill(6), float(position_pct))

            m = result["metrics"]
            st.subheader("绩效指标")
            c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
            c1.metric("总收益", f"{m['total_return']:.2%}")
            c2.metric("年化收益", f"{m['annual_return']:.2%}")
            c3.metric("最大回撤", f"{m['max_drawdown']:.2%}")
            c4.metric("夏普比率", f"{m['sharpe_ratio']:.2f}")
            c5.metric("胜率", f"{m['win_rate']:.2%}")
            c6.metric("盈亏比", f"{m['profit_loss_ratio']:.2f}")
            c7.metric("交易次数", f"{m['total_trades']}")

            st.plotly_chart(build_result_charts(result, df_signal, code_input), use_container_width=True)

            trades = result["trades"]
            if not trades.empty:
                st.subheader("交易明细")
                st.dataframe(trades, use_container_width=True)
            else:
                st.info("该参数组合下没有产生交易，可尝试放宽参数（如降低 ADX 阈值）")
        except DataFetchError as e:
            st.error(f"数据获取失败: {e}")
        except Exception as e:
            st.error(f"发生错误: {e}")
