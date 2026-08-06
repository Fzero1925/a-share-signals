import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.settings import PORTFOLIO_DIR
from core.data_manager import DataFetchError, DataManager
from core.indicators import add_all_indicators
from core.portfolio import PortfolioManager
from core.strategy_engine import STRATEGY_REGISTRY, get_strategy

ACCOUNT_FILE = os.path.join(PORTFOLIO_DIR, "paper_account.json")


@st.cache_data(ttl=1800, show_spinner=False)
def load_data(code: str):
    dm = DataManager()
    df = dm.get_daily(code, "20240101", None)
    return add_all_indicators(df)


@st.cache_data(ttl=1800, show_spinner=False)
def load_stock_list():
    dm = DataManager()
    try:
        return dm.get_stock_list()
    except DataFetchError:
        return pd.DataFrame(columns=["code", "name"])


def get_latest_price(df: pd.DataFrame) -> float:
    return float(df["close"].iloc[-1])


def generate_daily_signals(strategy_name: str, params: dict, codes: list[str]) -> list[dict]:
    strategy = get_strategy(strategy_name, params)
    signals = []
    for code in codes:
        try:
            df = load_data(code)
            if df.empty or len(df) < 60:
                continue
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
            elif prev["position"] == 1 and latest["position"] == 1:
                action = "HOLD"
                reason = "持仓中"
            signals.append(
                {
                    "code": code,
                    "action": action,
                    "price": round(latest["close"], 2),
                    "pct_change": round((latest["close"] / prev["close"] - 1) * 100, 2),
                    "reason": reason,
                    "position": int(latest["position"]),
                }
            )
        except Exception:
            continue
    return signals


def show():
    st.title("💰 模拟盘交易")

    pm = PortfolioManager()
    if os.path.exists(ACCOUNT_FILE):
        pm.load_state(ACCOUNT_FILE)

    st.subheader("账户总览")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("初始资金", f"{pm.initial_capital:,.2f}")
    c2.metric("现金", f"{pm.cash:,.2f}")

    codes_held = list(pm.get_all_positions().keys())
    current_prices = {}
    for code in codes_held:
        try:
            df = load_data(code)
            current_prices[code] = get_latest_price(df)
        except Exception:
            continue
    pos_value = pm.get_position_value(current_prices)
    total_equity = pm.get_total_equity(current_prices)
    c3.metric("持仓市值", f"{pos_value:,.2f}")
    c4.metric("总资产", f"{total_equity:,.2f}")
    c5.metric("总收益率", f"{total_equity / pm.initial_capital - 1:.2%}")
    c6.metric("持仓数", f"{len(pm.get_all_positions())}")

    st.markdown("---")

    col1, col2, col3 = st.columns([1.2, 2, 1])
    with col1:
        strategy_name = st.selectbox("选择策略", list(STRATEGY_REGISTRY.keys()))
    with col2:
        codes_input = st.text_input(
            "监控股票池（逗号分隔）",
            value="600519,000001,300750,601318,600036",
            placeholder="600519,000001,300750",
        )
    with col3:
        st.write("")
        st.write("")
        signal_btn = st.button("🔄 生成今日信号", type="primary")

    if signal_btn:
        codes = [c.strip().zfill(6) for c in codes_input.split(",") if c.strip()]
        strategy = get_strategy(strategy_name)
        signals = generate_daily_signals(strategy_name, strategy.get_default_params(), codes)

        stock_list = load_stock_list()
        name_map = {}
        if stock_list is not None and not stock_list.empty:
            name_map = dict(zip(stock_list["code"], stock_list["name"]))

        rows = []
        for s in signals:
            name = name_map.get(s["code"], s["code"])
            held = pm.get_position(s["code"])
            shares = 0
            if s["action"] == "BUY":
                invest = total_equity * 0.2
                shares = int(invest / s["price"] / 100) * 100
            rows.append(
                {
                    "代码": s["code"],
                    "名称": name,
                    "信号": s["action"],
                    "现价": s["price"],
                    "涨跌幅%": s["pct_change"],
                    "建议股数": shares if s["action"] == "BUY" else "",
                    "触发原因": s["reason"],
                    "当前持仓": f"{held['shares']}股" if held else "无",
                }
            )
        st.subheader("📊 今日信号推荐")
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

        buys = [s for s in signals if s["action"] == "BUY"]
        sells = [s for s in signals if s["action"] == "SELL"]
        st.write(f"买入信号 {len(buys)} 个，卖出信号 {len(sells)} 个")

        c1, c2 = st.columns(2)
        if c1.button("✅ 执行全部买入信号", type="primary"):
            executed = 0
            for s in buys:
                df = load_data(s["code"])
                price = get_latest_price(df)
                invest = total_equity * 0.2
                shares = int(invest / price / 100) * 100
                if shares >= 100:
                    if pm.buy(s["code"], price, shares, str(df["date"].iloc[-1].date()), s["reason"]):
                        executed += 1
            st.success(f"已执行 {executed} 笔买入")
            pm.save_state(ACCOUNT_FILE)
            st.rerun()
        if c2.button("✅ 执行全部卖出信号"):
            executed = 0
            for s in sells:
                if pm.get_position(s["code"]):
                    df = load_data(s["code"])
                    price = get_latest_price(df)
                    if pm.sell(s["code"], price, str(df["date"].iloc[-1].date()), s["reason"]):
                        executed += 1
            st.success(f"已执行 {executed} 笔卖出")
            pm.save_state(ACCOUNT_FILE)
            st.rerun()

    st.markdown("---")

    st.subheader("💼 当前持仓")
    positions = pm.get_all_positions()
    if positions:
        rows = []
        for code, pos in positions.items():
            price = current_prices.get(code, pos["entry_price"])
            pnl = (price - pos["entry_price"]) * pos["shares"]
            pnl_pct = price / pos["entry_price"] - 1
            rows.append(
                {
                    "代码": code,
                    "股数": pos["shares"],
                    "成本价": round(pos["entry_price"], 3),
                    "现价": round(price, 3),
                    "盈亏额": round(pnl, 2),
                    "盈亏%": f"{pnl_pct:.2%}",
                    "买入日期": pos["entry_date"],
                    "买入原因": pos["reason"],
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("当前无持仓")

    st.markdown("---")

    st.subheader("📈 资金曲线")
    history = pm.get_trade_history()
    if history:
        dates = []
        equity = []
        running_cash = pm.initial_capital
        for t in history:
            dates.append(t["date"])
            if t["action"] == "BUY":
                running_cash -= t["price"] * t["shares"] + t["cost"]
            else:
                running_cash += t["price"] * t["shares"] - t["cost"]
            equity.append(running_cash)
        fig = go.Figure(
            go.Scatter(x=dates, y=equity, mode="lines+markers", name="账户权益", line=dict(color="blue"))
        )
        fig.update_layout(height=350, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("暂无交易记录")

    st.markdown("---")

    st.subheader("📋 交易历史")
    if history:
        hist_df = pd.DataFrame(history)
        hist_df["pnl"] = hist_df["pnl"].fillna(0)
        st.dataframe(hist_df, use_container_width=True)
    else:
        st.info("暂无交易记录")
