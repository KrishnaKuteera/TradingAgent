import sys
import os
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="My Portfolio", page_icon="💼", layout="wide")

PORTFOLIO_USER = "Nanda"

# --- Auth guard ---
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page first.")
    st.stop()

if st.session_state.get("username", "").lower() != PORTFOLIO_USER.lower():
    st.error("Access denied.")
    st.stop()

# --- Portfolio module path ---
_here            = os.path.dirname(os.path.abspath(__file__))
_portfolio_local = os.path.join(_here, '..', '..', 'PortfolioReport')
_portfolio_cloud = os.path.join(_here, '..', 'PortfolioReport')
_portfolio_path  = _portfolio_local if os.path.isdir(_portfolio_local) else _portfolio_cloud
sys.path.insert(0, _portfolio_path)

try:
    from src.data   import load_all_from_questrade, get_fx
    from src.calc   import get_all_symbols, load_sector_data, load_subsector_data, load_currency_overrides
    from src.report import build_html
except ImportError as e:
    st.error(f"Portfolio module not available: {e}")
    st.stop()


def _setup_tokens():
    try:
        if "questrade" in st.secrets:
            from pathlib import Path
            if "chandu_token" in st.secrets["questrade"]:
                Path("/tmp/ChanduAPITracker").write_text(st.secrets["questrade"]["chandu_token"])
            if "nandu_token" in st.secrets["questrade"]:
                Path("/tmp/NanduAPITracker").write_text(st.secrets["questrade"]["nandu_token"])
    except Exception:
        pass


# --- Page ---
st.title("💼 My Portfolio")

col1, col2 = st.columns([1, 5])
with col1:
    refresh = st.button("🔄 Refresh", use_container_width=True)

if refresh:
    st.cache_data.clear()

_setup_tokens()

with st.spinner("Fetching live data from Questrade..."):
    try:
        chandu_data, nandu_data, errors = load_all_from_questrade()

        stale = [msg for person, msg in errors if person == "__stale__"]
        if stale:
            st.warning(f"⚠️ Live data unavailable — showing cached snapshot from {stale[0]}. "
                       "Update the Questrade token in Streamlit secrets and refresh.")
        errors = [(p, m) for p, m in errors if p != "__stale__"]

        fx = get_fx(chandu_data)

        for data in [chandu_data, nandu_data]:
            if "Positions" in data and not data["Positions"].empty:
                pos_df = data["Positions"]
                mask   = ~pos_df["Equity Description"].str.upper().str.contains("DOLLAR|CASH", na=False)
                data["Positions"] = pos_df[mask].reset_index(drop=True)

        symbols            = get_all_symbols(chandu_data, nandu_data)
        sector_data        = load_sector_data(symbols)
        subsector_data     = load_subsector_data()
        currency_overrides = load_currency_overrides()
        report_date        = datetime.today().strftime("%d %b %Y")

        from src.fmp import fetch_market_quotes
        market_quotes = fetch_market_quotes(["SPY", "QQQ"])

        html = build_html(chandu_data, nandu_data, report_date, fx,
                          sector_data, subsector_data, currency_overrides, errors,
                          market_quotes=market_quotes)
        st.components.v1.html(html, height=900, scrolling=True)

    except Exception as e:
        st.error(f"Failed to load portfolio: {e}")
