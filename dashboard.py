import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import json
import os
import bcrypt
import pytz

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
        json_file = 'tradeportfolioagent-52f42fe31773.json'

        # Try local JSON file first (for local development)
        if os.path.exists(json_file):
            credentials = Credentials.from_service_account_file(json_file, scopes=SCOPES)
        # Fall back to Streamlit secrets (for cloud deployment)
        elif "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        else:
            st.error("❌ Service account credentials not found. Please ensure tradeportfolioagent-52f42fe31773.json exists in this directory.")
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
def fetch_tickers_with_sectors():
    """Fetch tickers and their sectors from 'Tickers' tab (caching for 5 min)"""
    try:
        client = get_gspread_client()
        spreadsheet = client.open('StockTracker')

        # Try to get the 'Tickers' worksheet
        try:
            worksheet = spreadsheet.worksheet('Tickers')
        except:
            worksheet = spreadsheet.sheet1

        all_values = worksheet.get_all_values()

        if not all_values:
            return [], {}

        headers = [h.lower().strip() for h in all_values[0]]
        ticker_idx = headers.index('ticker') if 'ticker' in headers else 0

        tickers = []
        for row in all_values[1:]:
            if row and len(row) > ticker_idx and row[ticker_idx].strip():
                tickers.append(row[ticker_idx].strip().upper())

        # Fetch sector, sub-sector, and description from yfinance
        sectors = {}
        sub_sectors = {}
        descriptions = {}
        for ticker in tickers:
            try:
                info = yf.Ticker(ticker).info
                sector = info.get('sector', 'Unknown')
                industry = info.get('industry', 'Unknown')
                # Get business description - try multiple fields
                desc = info.get('longBusinessSummary', '')
                if not desc:
                    desc = info.get('businessSummary', '')
                # Limit description to first 150 characters for readability
                if desc:
                    desc = desc[:150].rstrip() + '...' if len(desc) > 150 else desc
                else:
                    desc = 'N/A'

                sectors[ticker] = sector if sector else 'Unknown'
                sub_sectors[ticker] = industry if industry else 'Unknown'
                descriptions[ticker] = desc
            except:
                sectors[ticker] = 'Unknown'
                sub_sectors[ticker] = 'Unknown'
                descriptions[ticker] = 'N/A'

        return tickers, sectors, sub_sectors, descriptions
    except Exception as e:
        st.error(f"Error fetching tickers: {str(e)}")
        return [], {}, {}

@st.cache_data(ttl=300)
def fetch_tickers():
    """Fetch tickers from 'Tickers' tab (backward compatibility)"""
    tickers, _, _, _ = fetch_tickers_with_sectors()
    return tickers

# Analyze stocks with CANSLIM metrics
def analyze_stocks(tickers):
    """Analyze stocks for buy zone signals + CANSLIM metrics"""
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Download SPY for RS Rating calculation (once at the start)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    try:
        spy_data = yf.download('SPY', start=start_date, end=end_date, progress=False)
        spy_return = ((spy_data['Close'].iloc[-1] - spy_data['Close'].iloc[0]) / spy_data['Close'].iloc[0]) * 100
    except:
        spy_return = 10  # Default fallback
        spy_data = None

    # Calculate RS Ratings for all tickers first (for ranking)
    rs_ratings = {}
    for idx, ticker in enumerate(tickers):
        status_text.text(f"Calculating RS Rating... {ticker} ({idx+1}/{len(tickers)})")
        try:
            data_365 = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if len(data_365) > 0:
                ticker_return = ((data_365['Close'].iloc[-1] - data_365['Close'].iloc[0]) / data_365['Close'].iloc[0]) * 100
                rs_value = (ticker_return / spy_return) * 100 if spy_return != 0 else 50
                rs_ratings[ticker] = rs_value
            else:
                rs_ratings[ticker] = 0
        except:
            rs_ratings[ticker] = 0

    # Rank RS ratings and convert to 1-99 scale
    sorted_rs = sorted(rs_ratings.items(), key=lambda x: x[1], reverse=True)
    rs_rank = {ticker: int((i / len(tickers)) * 99) + 1 for i, (ticker, _) in enumerate(sorted_rs)}

    # Analyze individual stocks
    for idx, ticker in enumerate(tickers):
        status_text.text(f"Analyzing {ticker}... ({idx+1}/{len(tickers)})")
        progress_bar.progress((idx + 1) / len(tickers))

        try:
            end_date = datetime.now()
            start_date_100 = end_date - timedelta(days=100)
            start_date_252 = end_date - timedelta(days=252)

            # Download 252 days of data for all calculations
            data = yf.download(ticker, start=start_date_252, end=end_date, progress=False)

            if len(data) == 0:
                results.append({
                    'Ticker': ticker,
                    'Status': '⚠️ No Data',
                    'Current Price': 'N/A',
                    '50-DMA': 'N/A',
                    'Distance from 50-DMA': 'N/A',
                    'Signal': 'No Data',
                    'Buy Zone': False,
                    'RS Rating': 0,
                    'Above 200-DMA': False,
                    'Volume Surge': False,
                    '52W High %': 0,
                    'Above Pivot': False
                })
                continue

            # Extract current price and moving averages
            current_price = data['Close'].iloc[-1].item() if hasattr(data['Close'].iloc[-1], 'item') else float(data['Close'].iloc[-1])
            sma_50 = data['Close'].tail(50).mean().item() if hasattr(data['Close'].tail(50).mean(), 'item') else float(data['Close'].tail(50).mean())
            sma_200 = data['Close'].tail(200).mean().item() if hasattr(data['Close'].tail(200).mean(), 'item') else float(data['Close'].tail(200).mean())

            high_52w = data['High'].tail(252).max().item() if hasattr(data['High'].tail(252).max(), 'item') else float(data['High'].tail(252).max())
            low_52w = data['Low'].tail(252).min().item() if hasattr(data['Low'].tail(252).min(), 'item') else float(data['Low'].tail(252).min())
            recent_high = data['High'].tail(20).max().item() if hasattr(data['High'].tail(20).max(), 'item') else float(data['High'].tail(20).max())
            recent_low = data['Low'].tail(20).min().item() if hasattr(data['Low'].tail(20).min(), 'item') else float(data['Low'].tail(20).min())
            pivot_high = data['High'].tail(10).max().item() if hasattr(data['High'].tail(10).max(), 'item') else float(data['High'].tail(10).max())

            # Volume calculations
            today_volume = data['Volume'].iloc[-1].item() if hasattr(data['Volume'].iloc[-1], 'item') else float(data['Volume'].iloc[-1])
            avg_50_volume = data['Volume'].tail(50).mean().item() if hasattr(data['Volume'].tail(50).mean(), 'item') else float(data['Volume'].tail(50).mean())

            # Distance calculations
            distance_from_dma = ((current_price - sma_50) / sma_50) * 100
            high_52w_pct = ((high_52w - current_price) / high_52w) * 100 if high_52w > 0 else 0

            recent_range = recent_high - recent_low
            hist_range = high_52w - low_52w
            range_compression = (recent_range / hist_range) * 100 if hist_range > 0 else 0

            # CANSLIM Flags
            above_200_dma = current_price > sma_200
            volume_surge = today_volume > (avg_50_volume * 1.5)
            above_pivot = current_price > pivot_high
            rs_rating_value = rs_rank.get(ticker, 50)

            # CANSLIM Screening Logic
            canslim_score = 0
            canslim_signals = []

            # L - Leader (RS Rating > 70)
            if rs_rating_value > 70:
                canslim_score += 1
                canslim_signals.append("L")

            # S - Supply/Demand (Volume Surge)
            if volume_surge:
                canslim_score += 1
                canslim_signals.append("S")

            # M - Market (Above 200-DMA)
            if above_200_dma:
                canslim_score += 1
                canslim_signals.append("M")

            # N - New Highs/Pivot
            if above_pivot or high_52w_pct < 10:
                canslim_score += 1
                canslim_signals.append("N")

            # A/C/I - Will need external data (not in daily OHLCV)
            # For now, we flag stocks that meet L+S+M+N

            is_buy_zone = canslim_score >= 3  # Passes if 3+ CANSLIM criteria met
            signals = [f"CANSLIM: {', '.join(canslim_signals)}" if canslim_signals else "No CANSLIM Match"]

            results.append({
                'Ticker': ticker,
                'Match': '✅' if is_buy_zone else '❌',
                'Price': f"${current_price:.2f}",
                'RS': rs_rating_value,
                'Vol Surge': '✅' if volume_surge else '❌',
                'Trend (M)': '✅' if above_200_dma else '❌',
                'Pivot': '✅' if above_pivot else '❌',
                '52W High %': f"{high_52w_pct:.1f}%",
                'CANSLIM': ' '.join(canslim_signals) if canslim_signals else 'N/A',
                'Score': canslim_score,
                'Buy Zone': is_buy_zone
            })

        except Exception as e:
            results.append({
                'Ticker': ticker,
                'Match': '❌',
                'Price': 'Error',
                'RS': 0,
                'Vol Surge': '❌',
                'Trend (M)': '❌',
                'Pivot': '❌',
                '52W High %': 'N/A',
                'CANSLIM': 'Error',
                'Score': 0,
                'Buy Zone': False
            })

    progress_bar.empty()
    status_text.empty()
    return results

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
def display_sector_subsector_breakdown(df, sectors, sub_sectors, descriptions):
    """Display stocks in simple sector, industry, and description table"""
    sector_data = []

    for _, row in df.iterrows():
        ticker = row['Ticker']
        sector = sectors.get(ticker, 'Unknown')
        industry = sub_sectors.get(ticker, 'Unknown')
        description = descriptions.get(ticker, 'N/A')

        sector_data.append({
            'Ticker': ticker,
            'Sector': sector,
            'Industry': industry,
            'What They Do': description,
            'Price': row.get('Price', 'N/A'),
            'RS': row.get('RS', 0),
            'Match': row.get('Match', '❌')
        })

    sector_df = pd.DataFrame(sector_data).sort_values(['Sector', 'Industry', 'Ticker'])
    st.dataframe(sector_df, use_container_width=True, hide_index=True,
                column_config={
                    "Ticker": st.column_config.TextColumn(width="small"),
                    "Sector": st.column_config.TextColumn(width="medium"),
                    "Industry": st.column_config.TextColumn(width="medium"),
                    "What They Do": st.column_config.TextColumn(width="large"),
                    "Price": st.column_config.TextColumn(width="small"),
                    "RS": st.column_config.NumberColumn(width="small", format="%d"),
                    "Match": st.column_config.TextColumn(width="small"),
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
        _, sectors, sub_sectors, _ = fetch_tickers_with_sectors()

        sector_counts = {}
        for ticker in df['Ticker']:
            if ticker in sectors:
                sector = sectors[ticker]
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
        tab_canslim, tab_sectors = st.tabs(["📊 CANSLIM Analysis", "🏭 Sectors & Industries"])

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
            st.markdown("Stocks grouped by industry classification from Yahoo Finance:")
            _, sectors, sub_sectors, descriptions = fetch_tickers_with_sectors()
            display_sector_subsector_breakdown(df, sectors, sub_sectors, descriptions)

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
