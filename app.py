import streamlit as st

st.set_page_config(
    page_title="A股模拟盘回测系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.theme import setup_theme

setup_theme()

st.sidebar.title("A股模拟盘回测系统")

page = st.sidebar.radio(
    "导航",
    ["📊 数据浏览", "📈 策略回测", "💰 模拟盘交易"],
)

if page == "📊 数据浏览":
    from ui.page_data import show
elif page == "📈 策略回测":
    from ui.page_backtest import show
elif page == "💰 模拟盘交易":
    from ui.page_paper_trading import show

show()
