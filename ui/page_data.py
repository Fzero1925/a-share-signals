import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core.data_manager import DataFetchError, DataManager
from core.indicators import add_all_indicators


@st.cache_data(ttl=3600, show_spinner=False)
def load_data(code: str, start: str, end: str):
    dm = DataManager()
    return dm.get_daily(code, start, end)


def load_stock_list():
    dm = DataManager()
    try:
        return dm.get_stock_list()
    except DataFetchError:
        return pd.DataFrame(columns=["code", "name"])


def build_chart(df: pd.DataFrame, show_ma: bool, show_boll: bool, show_ema: bool) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03)

    fig.add_trace(
        go.Candlestick(
            x=df["date"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="K线",
            increasing_line_color="red",
            decreasing_line_color="green",
        ),
        row=1,
        col=1,
    )

    if show_ma:
        for col, color in [("ma5", "orange"), ("ma10", "blue"), ("ma20", "purple")]:
            if col in df.columns:
                fig.add_trace(
                    go.Scatter(x=df["date"], y=df[col], name=col.upper(), line=dict(color=color, width=1)),
                    row=1,
                    col=1,
                )
    if show_ema:
        for col, color in [("ema5", "cyan"), ("ema20", "magenta")]:
            if col in df.columns:
                fig.add_trace(
                    go.Scatter(x=df["date"], y=df[col], name=col.upper(), line=dict(color=color, width=1)),
                    row=1,
                    col=1,
                )
    if show_boll and "boll_upper" in df.columns:
        fig.add_trace(
            go.Scatter(x=df["date"], y=df["boll_upper"], name="BOLL上轨", line=dict(color="gray", width=1, dash="dot")),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=df["date"], y=df["boll_lower"], name="BOLL下轨", line=dict(color="gray", width=1, dash="dot"), fill="tonexty"),
            row=1,
            col=1,
        )

    colors = ["red" if c >= o else "green" for c, o in zip(df["close"], df["open"])]
    fig.add_trace(
        go.Bar(x=df["date"], y=df["volume"], name="成交量", marker_color=colors),
        row=2,
        col=1,
    )

    fig.update_layout(
        height=650,
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=40, b=10),
    )
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)
    return fig


def show():
    st.title("📊 数据浏览")

    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        code_input = st.text_input("股票代码", value="600519", placeholder="如 600519 或 000001")
    with col2:
        start_date = st.text_input("开始日期", value="20230101", placeholder="YYYYMMDD")
    with col3:
        end_date = st.text_input("结束日期", value="20251231", placeholder="YYYYMMDD")
    with col4:
        st.write("")
        st.write("")
        fetch_btn = st.button("获取数据", type="primary")

    stock_list = load_stock_list()
    if code_input and stock_list is not None and not stock_list.empty:
        code = code_input.strip().zfill(6)
        match = stock_list[stock_list["code"] == code]
        if not match.empty:
            st.caption(f"当前股票: {match.iloc[0]['name']} ({code})")

    if fetch_btn:
        try:
            df = load_data(code_input.strip().zfill(6), start_date, end_date)
            if df.empty:
                st.warning("所选日期范围内无数据")
                return
            df = add_all_indicators(df)

            st.subheader("技术指标叠加")
            c1, c2, c3 = st.columns(3)
            show_ma = c1.checkbox("均线 MA5/10/20", value=True)
            show_ema = c2.checkbox("EMA5/20", value=False)
            show_boll = c3.checkbox("布林带 BOLL", value=False)

            st.plotly_chart(build_chart(df, show_ma, show_boll, show_ema), use_container_width=True)

            st.subheader("最新技术指标")
            last = df.iloc[-1]
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("收盘价", f"{last['close']:.2f}")
            m2.metric("RSI(14)", f"{last['rsi14']:.1f}")
            m3.metric("ADX(14)", f"{last['adx14']:.1f}")
            m4.metric("MACD DIF", f"{last['macd_dif']:.3f}")
            m5.metric("MACD DEA", f"{last['macd_dea']:.3f}")
            m6.metric("ATR(14)", f"{last['atr14']:.2f}")

            with st.expander("查看原始数据"):
                st.dataframe(df, use_container_width=True)
        except DataFetchError as e:
            st.error(f"数据获取失败: {e}")
        except Exception as e:
            st.error(f"发生错误: {e}")
