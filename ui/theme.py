import streamlit as st

DARK_CSS = """
<style>
:root {
    --bg: #0e1117;
    --card-bg: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --text-dim: #8b949e;
    --accent: #58a6ff;
}
[data-testid="stAppViewContainer"] { background-color: var(--bg); }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { background-color: #0d1117; border-right: 1px solid var(--border); }
[data-testid="stMetric"] {
    background-color: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 16px;
}
[data-testid="stMetricValue"] { color: var(--text); }
[data-testid="stMetricLabel"] { color: var(--text-dim); }
h1, h2, h3, h4 { color: var(--text) !important; }
p, span, label, .stMarkdown { color: var(--text); }
[data-testid="stExpander"] {
    background-color: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
}
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div, .stTextInput input, .stNumberInput input {
    background-color: var(--card-bg) !important;
    color: var(--text) !important;
    border-color: var(--border) !important;
}
[data-baseweb="tab-list"] { border-bottom-color: var(--border) !important; }
[data-baseweb="tab"] { color: var(--text-dim); }
[data-baseweb="tab"][aria-selected="true"] { color: var(--text) !important; }
button[kind="primary"] { background-color: var(--accent) !important; }
[data-testid="stDataFrame"] { color: var(--text); }
</style>
"""

LIGHT_CSS = """
<style>
[data-testid="stMetric"] {
    background-color: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 8px;
    padding: 12px 16px;
}
</style>
"""


def setup_theme():
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = False

    with st.sidebar:
        st.markdown("---")
        dark = st.toggle("🌙 深色模式", value=st.session_state.dark_mode, key="dark_toggle")
        st.session_state.dark_mode = dark

    if st.session_state.dark_mode:
        st.markdown(DARK_CSS, unsafe_allow_html=True)
    else:
        st.markdown(LIGHT_CSS, unsafe_allow_html=True)
