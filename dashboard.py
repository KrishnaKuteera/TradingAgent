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

# Fetch tickers and sectors from Tickers tab
@st.cache_data(ttl=300)
def fetch_tickers():
    """Fetch tickers from 'Tickers' tab in Google Sheets."""
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

        tickers = []
        for row in all_values[1:]:
            if row and len(row) > ticker_idx and row[ticker_idx].strip():
                tickers.append(row[ticker_idx].strip().upper())
        return tickers
    except Exception as e:
        st.error(f"Error fetching tickers: {str(e)}")
        return []

# Analyze stocks with CANSLIM metrics — delegates to shared screener module
def analyze_stocks(tickers):
    """Analyze stocks for buy zone signals + CANSLIM metrics."""
    if not _screener_available:
        st.error("Screener module not available. Check PortfolioReport/src/screener.py.")
        return []

    progress_bar = st.progress(0)
    status_text = st.empty()
    total = len(tickers)
    _counter = [0]

    def _on_status(msg):
        _counter[0] += 1
        status_text.text(msg)
        progress_bar.progress(min(_counter[0] / max(total, 1), 1.0))

    raw = run_canslim_screen(tickers, status_callback=_on_status)

    progress_bar.empty()
    status_text.empty()

    # Convert to the legacy column format the rest of dashboard.py expects
    results = []
    for r in raw:
        results.append({
            "Ticker":     r["ticker"],
            "Match":      "✅" if r["buy_zone"] else "❌",
            "Price":      f"${r['price']:.2f}" if r["price"] else "N/A",
            "RS":         r["rs"],
            "Vol Surge":  "✅" if r["vol_surge"] else "❌",
            "Trend (M)":  "✅" if r["above_200dma"] else "❌",
            "Pivot":      "✅" if r["near_pivot"] else "❌",
            "52W High %": f"{r['high_52w_pct']:.1f}%",
            "CANSLIM":    r["canslim_letters"],
            "Score":      r["score"],
            "Buy Zone":   r["buy_zone"],
            # Sector info now comes from FMP (not yfinance .info)
            "_sector":    r["sector"],
            "_industry":  r["industry"],
            "_name":      r["name"],
        })
    return results

# Calculate price changes for various time periods
def calculate_price_changes(tickers):
    """Calculate price percentage changes for 1D, 5D, 1M, 3M, 6M, 1Y, YTD"""
    price_data = []
    end_date = datetime.now(pytz.timezone('America/Toronto')).date()

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")

            if len(hist) == 0:
                continue

            current_price = hist['Close'].iloc[-1]

            # Calculate returns for each period
            changes = {'Ticker': ticker, 'Current': f"${current_price:.2f}"}

            # 1 Day
            if len(hist) >= 1:
                price_1d_ago = hist['Close'].iloc[-2] if len(hist) > 1 else hist['Close'].iloc[-1]
                changes['1D'] = ((current_price - price_1d_ago) / price_1d_ago) * 100

            # 5 Days
            if len(hist) >= 5:
                price_5d_ago = hist['Close'].iloc[-5]
                changes['5D'] = ((current_price - price_5d_ago) / price_5d_ago) * 100

            # 1 Month
            if len(hist) >= 21:
                price_1m_ago = hist['Close'].iloc[-21]
                changes['1M'] = ((current_price - price_1m_ago) / price_1m_ago) * 100

            # 3 Months
            if len(hist) >= 63:
                price_3m_ago = hist['Close'].iloc[-63]
                changes['3M'] = ((current_price - price_3m_ago) / price_3m_ago) * 100

            # 6 Months
            if len(hist) >= 126:
                price_6m_ago = hist['Close'].iloc[-126]
                changes['6M'] = ((current_price - price_6m_ago) / price_6m_ago) * 100

            # 1 Year
            if len(hist) >= 252:
                price_1y_ago = hist['Close'].iloc[-252]
                changes['1Y'] = ((current_price - price_1y_ago) / price_1y_ago) * 100

            # YTD (Year to Date)
            year_start = hist[hist.index.year == end_date.year]
            if len(year_start) > 0:
                price_ytd = year_start['Close'].iloc[0]
                changes['YTD'] = ((current_price - price_ytd) / price_ytd) * 100

            price_data.append(changes)
        except:
            continue

    return pd.DataFrame(price_data)

# Display CANSLIM badges for each stock
def display_canslim_badges(df):
    """Display CANSLIM indicators as a table"""
    canslim_cols = []
    for _, row in df.iterrows():
        rs_val = row.get('RS', 0)
        rs_flag = "✅ L" if rs_val > 70 else "❌ L"
        vol_flag = "✅ S" if row.get('Vol Surge', '❌') == '✅' else "❌ S"
        trend_flag = "✅ M" if row.get('Trend (M)', '❌') == '✅' else "❌ M"
        pivot_flag = "✅ N" if row.get('Pivot', '❌') == '✅' else "❌ N"

        canslim_cols.append({
            'Ticker': row['Ticker'],
            'L': rs_flag,
            'S': vol_flag,
            'M': trend_flag,
            'N': pivot_flag,
            'RS Score': rs_val,
            'CANSLIM': row.get('CANSLIM', 'N/A'),
            'Score': row.get('Score', 0)
        })

    return pd.DataFrame(canslim_cols)

# Display sector/sub-sector breakdown
def display_sector_subsector_breakdown(df):
    """Display stocks in simple sector, industry, and description table."""
    sector_data = []
    for _, row in df.iterrows():
        sector_data.append({
            'Ticker':   row['Ticker'],
            'Name':     row.get('_name', row['Ticker']),
            'Sector':   row.get('_sector', 'Unknown'),
            'Industry': row.get('_industry', 'Unknown'),
            'Price':    row.get('Price', 'N/A'),
            'RS':       row.get('RS', 0),
            'Match':    row.get('Match', '❌'),
        })

    sector_df = pd.DataFrame(sector_data).sort_values(['Sector', 'Industry', 'Ticker'])
    st.dataframe(sector_df, use_container_width=True, hide_index=True,
                column_config={
                    "Ticker":   st.column_config.TextColumn(width="small"),
                    "Name":     st.column_config.TextColumn(width="medium"),
                    "Sector":   st.column_config.TextColumn(width="medium"),
                    "Industry": st.column_config.TextColumn(width="medium"),
                    "Price":    st.column_config.TextColumn(width="small"),
                    "RS":       st.column_config.NumberColumn(width="small", format="%d"),
                    "Match":    st.column_config.TextColumn(width="small"),
                })

# ============= AUTHENTICATION UI =============
if not st.session_state.authenticated:
    st.title("🔐 Stock Buy Zone Analyzer - Login")

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("### Enter your credentials")

        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")

        if st.button("🔓 Login", use_container_width=True, type="primary"):
            # Fetch users (cached for 1 hour)
            users = fetch_users_from_sheet()

            if login(users, username, password):
                st.success(f"✅ Welcome, {st.session_state.user_name}!")
                st.rerun()
            else:
                st.error("❌ Invalid username or password")

        st.divider()
        st.info("💡 Contact the administrator to request access")

else:
    # ============= MAIN TRADING DASHBOARD (ONLY IF AUTHENTICATED) =============

    # Sidebar with user info and logout
    st.sidebar.markdown(f"### 👤 {st.session_state.user_name}")

    if st.sidebar.button("🚪 Logout", use_container_width=True):
        logout()
        st.rerun()

    st.sidebar.divider()
    st.sidebar.header("⚙️ Configuration")
    refresh_button = st.sidebar.button("🔄 Run Analysis", use_container_width=True)

    st.title("📊 StockScreener - CANSLIM Analyzer")
    st.markdown("""
    **CANSLIM Stock Screening System** (William O'Neill)
    - **L**: Leader stocks (RS Rating > 70)
    - **S**: Strong volume surge (1.5x average)
    - **M**: Uptrend (above 200-day moving average)
    - **N**: New highs/pivot breakout
    """)

    # Analysis logic
    if refresh_button or 'analysis_results' not in st.session_state:
        tickers = fetch_tickers()

        if tickers:
            st.info(f"📊 Found {len(tickers)} tickers to analyze")
            results = analyze_stocks(tickers)
            st.session_state.analysis_results = results
            toronto_tz = pytz.timezone('America/Toronto')
            st.session_state.last_update = datetime.now(toronto_tz)
        else:
            st.error("Could not fetch tickers from Google Sheets")
            st.stop()

    # Display results
    if 'analysis_results' in st.session_state:
        results = st.session_state.analysis_results
        df = pd.DataFrame(results)

        # Filter buy zone stocks
        buy_zone_stocks = df[df['Buy Zone'] == True].copy()
        no_signal_stocks = df[df['Buy Zone'] == False].copy()

        # Metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("✅ CANSLIM Match", len(buy_zone_stocks), f"of {len(df)}")

        with col2:
            leader_count = len(df[df['RS'] > 70])
            st.metric("📈 Leaders (L)", leader_count, f"{(leader_count/len(df)*100):.0f}%")

        with col3:
            vol_count = len(df[df['Vol Surge'] == '✅'])
            st.metric("📊 Vol Surge (S)", vol_count, f"{(vol_count/len(df)*100):.0f}%")

        with col4:
            st.metric("Last Update", st.session_state.last_update.strftime('%I:%M %p'),
                     st.session_state.last_update.strftime('%m/%d/%Y'))

        st.divider()

        # Sector Distribution Pie Chart
        st.subheader("📊 Stock Distribution by Sector")
        sector_counts = {}
        for _, row in df.iterrows():
            sector = row.get('_sector', 'Unknown')
            if sector:
                sector_counts[sector] = sector_counts.get(sector, 0) + 1

        if sector_counts:
            # Create pie chart
            fig = go.Figure(data=[go.Pie(
                labels=list(sector_counts.keys()),
                values=list(sector_counts.values()),
                hole=0.3
            )])
            fig.update_layout(
                title="Stocks by Sector",
                height=400,
                showlegend=True
            )
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # CANSLIM Match Stocks Section
        if len(buy_zone_stocks) > 0:
            st.subheader(f"✅ CANSLIM Matches ({len(buy_zone_stocks)} stocks)")

            canslim_display = buy_zone_stocks[['Ticker', 'Price', 'RS', 'Vol Surge', 'Trend (M)', 'Pivot', '52W High %', 'CANSLIM', 'Score']].copy()

            st.dataframe(
                canslim_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Ticker": st.column_config.TextColumn(width="small"),
                    "Price": st.column_config.TextColumn(width="small"),
                    "RS": st.column_config.NumberColumn(width="small", format="%d"),
                    "Vol Surge": st.column_config.TextColumn(width="small"),
                    "Trend (M)": st.column_config.TextColumn(width="small"),
                    "Pivot": st.column_config.TextColumn(width="small"),
                    "52W High %": st.column_config.TextColumn(width="small"),
                    "CANSLIM": st.column_config.TextColumn(width="medium"),
                    "Score": st.column_config.NumberColumn(width="small"),
                }
            )


        else:
            st.info("No stocks currently in buy zone. Check back later!")

        st.divider()

        # Additional Analysis Tabs
        tab_canslim, tab_sectors, tab_performance = st.tabs(["📊 CANSLIM Analysis", "🏭 Sectors & Industries", "📈 Price Performance"])

        with tab_canslim:
            st.subheader("CANSLIM Breakdown - Stock Screening Indicators")
            st.markdown("""
            **CANSLIM (William O'Neil) Criteria:**
            - **C** — Current Quarterly Earnings
            - **A** — Annual Earnings Growth
            - **N** — New Highs / Pivot Points
            - **S** — Supply & Demand (Volume Surge)
            - **L** — Leader (RS Rating > 70)
            - **I** — Institutional Sponsorship
            - **M** — Market Trend (Above 200-DMA)
            """)
            canslim_df = display_canslim_badges(df)
            st.dataframe(canslim_df, use_container_width=True, hide_index=True)

        with tab_sectors:
            st.subheader("Stock Distribution by Sector & Sub-sector")
            st.markdown("Stocks grouped by industry classification (via FMP):")
            display_sector_subsector_breakdown(df)

        with tab_performance:
            st.subheader("Price Performance (% Change)")
            st.markdown("Stock price percentage changes over various time periods")

            tickers_list = df['Ticker'].tolist()
            perf_df = calculate_price_changes(tickers_list)

            if len(perf_df) > 0:
                # Format percentage columns with color
                for col in ['1D', '5D', '1M', '3M', '6M', '1Y', 'YTD']:
                    if col in perf_df.columns:
                        perf_df[col] = perf_df[col].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A")

                st.dataframe(perf_df, use_container_width=True, hide_index=True,
                           column_config={
                               "Ticker": st.column_config.TextColumn(width="small"),
                               "Current": st.column_config.TextColumn(width="small"),
                               "1D": st.column_config.TextColumn(width="small"),
                               "5D": st.column_config.TextColumn(width="small"),
                               "1M": st.column_config.TextColumn(width="small"),
                               "3M": st.column_config.TextColumn(width="small"),
                               "6M": st.column_config.TextColumn(width="small"),
                               "1Y": st.column_config.TextColumn(width="small"),
                               "YTD": st.column_config.TextColumn(width="small"),
                           })
            else:
                st.warning("Unable to fetch price performance data")

        st.divider()

        # All stocks with filtering
        with st.expander("📊 View All Stocks", expanded=False):
            st.subheader("All Stocks Analysis")

            col1, col2, col3 = st.columns(3)

            with col1:
                show_buy_zone = st.checkbox("Buy Zone Only", value=False)

            with col2:
                sort_by = st.selectbox("Sort by", ["Ticker", "RS Score", "CANSLIM Score"])

            with col3:
                search = st.text_input("Search ticker", "")

            display_df = df.copy()

            if show_buy_zone:
                display_df = display_df[display_df['Buy Zone'] == True]

            if search:
                display_df = display_df[display_df['Ticker'].str.contains(search.upper())]

            if sort_by == "RS Score":
                display_df = display_df.sort_values('RS', ascending=False)
            elif sort_by == "CANSLIM Score":
                display_df = display_df.sort_values('Score', ascending=False)
            else:
                display_df = display_df.sort_values('Ticker')

            display_cols = display_df[['Ticker', 'Match', 'Price', 'RS', 'Vol Surge', 'Trend (M)', 'Pivot', 'CANSLIM', 'Score']]

            st.dataframe(display_cols, use_container_width=True, hide_index=True)

            csv = display_df.to_csv(index=False)
            toronto_tz = pytz.timezone('America/Toronto')
            current_time = datetime.now(toronto_tz).strftime('%Y%m%d_%H%M%S')
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"stock_analysis_{current_time}.csv",
                mime="text/csv"
            )

    st.divider()
    st.markdown(f"""
    <div style="text-align: center; color: #666; font-size: 12px; margin-top: 2rem;">
        <p>📊 StockScreener - CANSLIM Analyzer | Logged in as: {st.session_state.user_name}</p>
        <p>Data from Yahoo Finance | Google Sheets Integration</p>
    </div>
    """, unsafe_allow_html=True)
