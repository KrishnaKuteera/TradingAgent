import sys
import os
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import json
import bcrypt
import pytz

PORTFOLIO_USER = "Nanda"

# --- Shared screener (PortfolioReport/src/screener.py) ---
_here            = os.path.dirname(os.path.abspath(__file__))
_portfolio_local = os.path.join(_here, '..', 'PortfolioReport')
_portfolio_cloud = os.path.join(_here, 'PortfolioReport')
_portfolio_path  = _portfolio_local if os.path.isdir(_portfolio_local) else _portfolio_cloud
if _portfolio_path not in sys.path:
    sys.path.insert(0, _portfolio_path)

try:
    from src.screener import run_canslim_screen, to_dataframe as screener_to_df
    _screener_available = True
except ImportError:
    _screener_available = False

# Page configuration
st.set_page_config(
    page_title="StockScreener - CANSLIM Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .buy-zone {background-color: #d4edda; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #28a745;}
    .no-signal {background-color: #f8f9fa; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #6c757d;}
    .error {background-color: #f8d7da; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #f5222d;}
    .metric-card {
        background-color: #f0f2f6;
        padding: 1.5rem;
        border-radius: 0.5rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state for authentication
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'username' not in st.session_state:
    st.session_state.username = None

# Cache function for Google Sheets authentication
@st.cache_resource
def get_gspread_client():
    import os
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

    try:
        json_file = 'tradeportfolioagent-8348ccf38790.json'

        # Try local JSON file first (for local development)
        if os.path.exists(json_file):
            credentials = Credentials.from_service_account_file(json_file, scopes=SCOPES)
        # Fall back to Streamlit secrets (for cloud deployment)
        elif "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        else:
            st.error("❌ Service account credentials not found. Please ensure tradeportfolioagent-8348ccf38790.json exists in this directory.")
            st.stop()
    except Exception as e:
        st.error(f"❌ Authentication error: {str(e)}")
        st.stop()

    return gspread.authorize(credentials)

# Cache users for 5 minutes
@st.cache_data(ttl=300)
def fetch_users_from_sheet():
    """Fetch user credentials from 'Auth' tab in Google Sheet"""
    try:
        client = get_gspread_client()

        try:
            spreadsheet = client.open('StockTracker')
        except Exception as e:
            st.error(f"❌ Could not open spreadsheet 'StockTracker': {str(e)}")
            st.stop()

        # Try to get the 'Auth' worksheet
        try:
            auth_sheet = spreadsheet.worksheet('Auth')
        except Exception as e:
            st.error(f"❌ 'Auth' tab not found. Error: {str(e)}")
            st.stop()

        # Get all values from Auth sheet
        try:
            all_values = auth_sheet.get_all_values()
        except Exception as e:
            st.error(f"❌ Could not read Auth sheet: {str(e)}")
            st.stop()

        if not all_values or len(all_values) < 2:
            st.error("❌ 'Auth' tab is empty. Add users with: username, password")
            st.stop()

        # Parse header and users
        headers = all_values[0]
        users = []

        required_cols = ['username', 'password']
        optional_cols = ['email', 'name']
        header_lower = [h.lower().strip() for h in headers]

        # Check if all required columns exist
        for col in required_cols:
            if col not in header_lower:
                st.error(f"❌ Missing required column in Auth tab: '{col}'")
                st.stop()

        # Get column indices for required and optional columns
        col_indices = {col: header_lower.index(col) for col in required_cols}
        for col in optional_cols:
            if col in header_lower:
                col_indices[col] = header_lower.index(col)

        # Build user list
        for row in all_values[1:]:
            # Skip empty rows
            if not row or not row[0].strip():
                continue

            # Check if row has enough columns for required fields
            max_required_idx = max(col_indices[col] for col in required_cols)
            if len(row) <= max_required_idx:
                continue

            try:
                user_data = {
                    'username': row[col_indices['username']].strip(),
                    'password': row[col_indices['password']].strip(),
                }
                if 'email' in col_indices and len(row) > col_indices['email']:
                    user_data['email'] = row[col_indices['email']].strip()
                if 'name' in col_indices and len(row) > col_indices['name']:
                    user_data['name'] = row[col_indices['name']].strip()
                users.append(user_data)
            except (IndexError, AttributeError):
                continue

        if not users:
            st.error("❌ No users found in Auth tab")
            st.stop()

        return users

    except Exception as e:
        st.error(f"❌ Error fetching users: {str(e)}")
        st.stop()

# Validate password (supports both plain text and bcrypt hashes)
def validate_password(stored_password, provided_password):
    """Validate password against stored hash or plain text"""
    try:
        # Check if stored password is a bcrypt hash (starts with $2)
        if stored_password.startswith('$2'):
            return bcrypt.checkpw(
                provided_password.encode('utf-8'),
                stored_password.encode('utf-8')
            )
        else:
            # Fall back to plain text comparison (for initial setup)
            return stored_password == provided_password
    except:
        return False

# Login function
def login(users, username, password):
    """Authenticate user against user list"""
    username_lower = username.lower().strip()
    for user in users:
        if user['username'].lower().strip() == username_lower:
            if validate_password(user['password'], password):
                st.session_state.authenticated = True
                st.session_state.username = username
                st.session_state.user_name = user['username']
                return True
    return False

# Logout function
def logout():
    """Logout user"""
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.user_name = None

# Fetch tickers from Google Sheets Tickers tab
@st.cache_data(ttl=300)
def fetch_tickers():
    try:
        client = get_gspread_client()
        spreadsheet = client.open('StockTracker')
        try:
            worksheet = spreadsheet.worksheet('Tickers')
        except Exception:
            worksheet = spreadsheet.sheet1
        all_values = worksheet.get_all_values()
        if not all_values:
            return []
        headers = [h.lower().strip() for h in all_values[0]]
        ticker_idx = headers.index('ticker') if 'ticker' in headers else 0
        return [row[ticker_idx].strip().upper()
                for row in all_values[1:]
                if row and len(row) > ticker_idx and row[ticker_idx].strip()]
    except Exception as e:
        st.error(f"Error fetching tickers: {str(e)}")
        return []


# Fetch rules from Google Sheets (same sheet as portfolio analysis)
def _load_rules():
    try:
        import importlib.util
        _here = os.path.dirname(os.path.abspath(__file__))
        _rules_path = os.path.join(_here, 'src', 'rules_sheet.py')
        spec = importlib.util.spec_from_file_location("rules_sheet", _rules_path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.fetch_rules, mod.save_rule, True
    except Exception:
        return None, None, False


# Price performance table (kept dashboard-only)
def _calculate_price_changes(tickers):
    price_data = []
    end_date = datetime.now(pytz.timezone('America/Toronto')).date()
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period="1y")
            if len(hist) == 0:
                continue
            current_price = hist['Close'].iloc[-1]
            changes = {'Ticker': ticker, 'Current': f"${current_price:.2f}"}
            periods = {'1D': 2, '5D': 5, '1M': 21, '3M': 63, '6M': 126, '1Y': 252}
            for label, n in periods.items():
                if len(hist) >= n:
                    past = hist['Close'].iloc[-n]
                    changes[label] = ((current_price - past) / past) * 100
            year_start = hist[hist.index.year == end_date.year]
            if len(year_start) > 0:
                changes['YTD'] = ((current_price - year_start['Close'].iloc[0])
                                  / year_start['Close'].iloc[0]) * 100
            price_data.append(changes)
        except Exception:
            continue
    return pd.DataFrame(price_data)


# ============= AUTHENTICATION UI =============
if not st.session_state.authenticated:
    st.title("🔐 Stock Buy Zone Analyzer - Login")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Enter your credentials")
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("🔓 Login", use_container_width=True, type="primary"):
            users = fetch_users_from_sheet()
            if login(users, username, password):
                st.success(f"✅ Welcome, {st.session_state.user_name}!")
                st.rerun()
            else:
                st.error("❌ Invalid username or password")
        st.divider()
        st.info("💡 Contact the administrator to request access")

else:
    # ============= MAIN DASHBOARD =============
    from src.ui import render_holdings_matrix, render_action_items, render_rule_settings
    from src.signals import run_signals_watchlist

    st.sidebar.markdown(f"### 👤 {st.session_state.user_name}")
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        logout()
        st.rerun()

    st.sidebar.divider()
    st.sidebar.header("⚙️ Configuration")
    refresh_button = st.sidebar.button("🔄 Run Analysis", use_container_width=True)

    st.title("📊 StockScreener — O'Neil / CAN SLIM")

    fetch_rules, save_rule, rules_available = _load_rules()
    rules = []
    if rules_available:
        try:
            rules = fetch_rules()
        except Exception as e:
            st.warning(f"Could not load rules: {e}")

    tab_analysis, tab_rules = st.tabs(["📊 Analysis & Actions", "⚙️ Rule Settings"])

    with tab_rules:
        st.header("⚙️ Rule Settings")
        st.markdown("Same rules applied to your portfolio — view-only here, changes save via the portfolio page.")
        if rules:
            render_rule_settings(rules, save_rule_fn=None)
        else:
            st.warning("Rules not available. Check that the **Rules** tab exists in StockTracker.")

    with tab_analysis:
        col1, col2 = st.columns([1, 1])
        with col1:
            run_btn = st.button("▶️ Run Analysis", type="primary", use_container_width=True)
        with col2:
            if st.button("🗑️ Clear", use_container_width=True):
                st.session_state.pop("watchlist_result", None)
                st.session_state.pop("watchlist_ts", None)
                st.rerun()

        if "watchlist_ts" in st.session_state:
            st.caption(f"Last run: {st.session_state['watchlist_ts']}")

        if run_btn or refresh_button or "watchlist_result" in st.session_state:
            if run_btn or refresh_button:
                tickers = fetch_tickers()
                if not tickers:
                    st.error("No tickers found in Google Sheets.")
                    st.stop()
                st.info(f"📊 Analyzing {len(tickers)} watchlist stocks against all O'Neil rules…")
                with st.spinner("Fetching live technical data… (30–60 sec)"):
                    result = run_signals_watchlist(tickers, rules)
                    st.session_state["watchlist_result"] = result
                    st.session_state["watchlist_ts"] = datetime.now(
                        pytz.timezone('America/Toronto')).strftime('%d %b %Y %I:%M %p')

            result   = st.session_state.get("watchlist_result", {})
            holdings = result.get("holdings", [])
            actions  = result.get("actions",  [])

            # Summary metrics
            if holdings:
                immediate = sum(1 for h in holdings if h["worst_urgency"] == "IMMEDIATE")
                this_week = sum(1 for h in holdings if h["worst_urgency"] == "THIS WEEK")
                ok        = sum(1 for h in holdings if h["worst_urgency"] == "NONE")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total Stocks", len(holdings))
                col2.metric("🔴 Immediate",  immediate)
                col3.metric("🟡 This Week",  this_week)
                col4.metric("✅ OK",          ok)

            # Holdings matrix
            st.header("📋 All Stocks — Rule Results")
            render_holdings_matrix(holdings, rules, show_account=False)

            st.divider()

            # Action items
            st.header("🎯 Action Items")
            render_action_items(actions, show_account=False)

            st.divider()

            # Price performance tab
            with st.expander("📈 Price Performance", expanded=False):
                tickers_list = [h["symbol"] for h in holdings]
                perf_df = _calculate_price_changes(tickers_list)
                if len(perf_df) > 0:
                    for col in ['1D', '5D', '1M', '3M', '6M', '1Y', 'YTD']:
                        if col in perf_df.columns:
                            perf_df[col] = perf_df[col].apply(
                                lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A")
                    st.dataframe(perf_df, use_container_width=True, hide_index=True)
                else:
                    st.warning("Unable to fetch price performance data.")

        else:
            st.info("Click **▶️ Run Analysis** to evaluate all O'Neil rules against the watchlist.")

    st.divider()
    st.markdown(f"""
    <div style="text-align: center; color: #666; font-size: 12px; margin-top: 2rem;">
        <p>📊 StockScreener — O'Neil / CAN SLIM | Logged in as: {st.session_state.user_name}</p>
        <p>Data: Yahoo Finance (price) · FMP (sector) · Google Sheets (rules & watchlist)</p>
    </div>
    """, unsafe_allow_html=True)
