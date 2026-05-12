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

# Page configuration
st.set_page_config(
    page_title="Stock Buy Zone Analyzer",
    page_icon="📈",
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

        # Fetch sector and sub-sector (industry) data from yfinance
        sectors = {}
        sub_sectors = {}
        for ticker in tickers:
            try:
                info = yf.Ticker(ticker).info
                sector = info.get('sector', 'Unknown')
                industry = info.get('industry', 'Unknown')
                sectors[ticker] = sector if sector else 'Unknown'
                sub_sectors[ticker] = industry if industry else 'Unknown'
            except:
                sectors[ticker] = 'Unknown'
                sub_sectors[ticker] = 'Unknown'

        return tickers, sectors, sub_sectors
    except Exception as e:
        st.error(f"Error fetching tickers: {str(e)}")
        return [], {}, {}

@st.cache_data(ttl=300)
def fetch_tickers():
    """Fetch tickers from 'Tickers' tab (backward compatibility)"""
    tickers, _, _ = fetch_tickers_with_sectors()
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

            # Buy Zone Logic
            is_buy_zone = False
            signals = []

            if abs(distance_from_dma) <= 3:
                is_buy_zone = True
                signals.append("📍 Within 3% of 50-DMA")

            if range_compression < 30:
                is_buy_zone = True
                signals.append("📦 Tight Range (VCP)")

            if above_200_dma:
                signals.append("⬆️ Above 200-DMA")

            if volume_surge:
                signals.append("📈 Vol Surge")

            if above_pivot:
                signals.append("🎯 Above Pivot")

            results.append({
                'Ticker': ticker,
                'Status': '✅' if is_buy_zone else '⭕',
                'Current Price': f"${current_price:.2f}",
                '50-DMA': f"${sma_50:.2f}",
                'Distance from 50-DMA': f"{distance_from_dma:+.2f}%",
                'Range Compression': f"{range_compression:.1f}%",
                'Signal': ' | '.join(signals) if signals else 'No Signal',
                'Buy Zone': is_buy_zone,
                'Distance_Value': distance_from_dma,
                'Range_Value': range_compression,
                'RS Rating': rs_rating_value,
                'Above 200-DMA': above_200_dma,
                'Volume Surge': volume_surge,
                '52W High %': high_52w_pct,
                'Above Pivot': above_pivot,
                'Pivot Point': f"${pivot_high:.2f}",
                'Sector': '',  # Will be filled later
                'Industry': ''  # Will be filled later
            })

        except Exception as e:
            results.append({
                'Ticker': ticker,
                'Status': '❌',
                'Current Price': 'Error',
                '50-DMA': 'Error',
                'Distance from 50-DMA': 'Error',
                'Signal': f'Error: {str(e)[:30]}',
                'Buy Zone': False,
                'RS Rating': 0,
                'Above 200-DMA': False,
                'Volume Surge': False,
                '52W High %': 0,
                'Above Pivot': False
            })

    progress_bar.empty()
    status_text.empty()
    return results

# Display CANSLIM badges for each stock
def display_canslim_badges(df):
    """Display CANSLIM indicators as a table"""
    canslim_cols = []
    for _, row in df.iterrows():
        rs_flag = "✅ L" if row.get('RS Rating', 0) > 70 else "❌ L"
        vol_flag = "✅ S" if row.get('Volume Surge', False) else "❌ S"
        trend_flag = "✅ M" if row.get('Above 200-DMA', False) else "❌ M"
        high_flag = "✅ N" if row.get('52W High %', 100) < 10 else "❌ N"
        pivot_flag = "✅ N" if row.get('Above Pivot', False) else "❌ N"

        canslim_cols.append({
            'Ticker': row['Ticker'],
            'RS (L)': rs_flag,
            'Vol (S)': vol_flag,
            'Trend (M)': trend_flag,
            'Near High (N)': high_flag,
            'Pivot (N)': pivot_flag,
            'RS Score': f"{row.get('RS Rating', 0):.0f}",
            '52W High %': f"{row.get('52W High %', 0):.1f}%"
        })

    return pd.DataFrame(canslim_cols)

# Display sector/sub-sector drill-down
def display_sector_subsector_breakdown(df, sectors, sub_sectors):
    """Display stocks grouped by sector and sub-sector"""
    sector_groups = {}

    for _, row in df.iterrows():
        ticker = row['Ticker']
        sector = sectors.get(ticker, 'Unknown')
        sub_sector = sub_sectors.get(ticker, 'Unknown')

        if sector not in sector_groups:
            sector_groups[sector] = {}
        if sub_sector not in sector_groups[sector]:
            sector_groups[sector][sub_sector] = []

        sector_groups[sector][sub_sector].append({
            'Ticker': ticker,
            'Price': row.get('Current Price', 'N/A'),
            'RS': row.get('RS Rating', 0),
            'Signal': row.get('Signal', 'No Signal')
        })

    for sector in sorted(sector_groups.keys()):
        with st.expander(f"📊 {sector} ({sum(len(tickers) for tickers in sector_groups[sector].values())} stocks)", expanded=False):
            for sub_sector in sorted(sector_groups[sector].keys()):
                st.subheader(f"  └─ {sub_sector}")
                sub_df = pd.DataFrame(sector_groups[sector][sub_sector])
                st.dataframe(sub_df, use_container_width=True, hide_index=True)

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

    st.title("📈 Stock Buy Zone Analyzer")
    st.markdown("""
    Analyze your stock portfolio to identify **buy zone opportunities**:
    - Stocks within **3% of 50-day moving average** (support levels)
    - Stocks with **tight price ranges** (VCP consolidation patterns)
    """)

    # Analysis logic
    if refresh_button or 'analysis_results' not in st.session_state:
        tickers = fetch_tickers()

        if tickers:
            st.info(f"📊 Found {len(tickers)} tickers to analyze")
            results = analyze_stocks(tickers)
            st.session_state.analysis_results = results
            st.session_state.last_update = datetime.now()
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
            st.markdown(f"""
            <div class="metric-card">
                <h3>✅ Buy Zone Stocks</h3>
                <h1>{len(buy_zone_stocks)}</h1>
                <p>out of {len(df)} total</p>
            </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <h3>📍 3% of 50-DMA</h3>
                <h1>{len(df[df['Signal'].str.contains('Within 3%', na=False)])}</h1>
                <p>Support levels</p>
            </div>
            """, unsafe_allow_html=True)

        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <h3>📦 VCP Patterns</h3>
                <h1>{len(df[df['Signal'].str.contains('Tight Range', na=False)])}</h1>
                <p>Consolidations</p>
            </div>
            """, unsafe_allow_html=True)

        with col4:
            st.markdown(f"""
            <div class="metric-card">
                <h3>⏰ Last Update</h3>
                <p>{st.session_state.last_update.strftime('%I:%M %p')}</p>
                <p>{st.session_state.last_update.strftime('%m/%d/%Y')}</p>
            </div>
            """, unsafe_allow_html=True)

        st.divider()

        # Sector Distribution Pie Chart
        st.subheader("📊 Stock Distribution by Sector")
        _, sectors, sub_sectors = fetch_tickers_with_sectors()

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

        # Buy Zone Stocks Section
        if len(buy_zone_stocks) > 0:
            st.subheader("🎯 Buy Zone Stocks (Action Zone)")

            buy_zone_display = buy_zone_stocks[['Ticker', 'Status', 'Current Price', '50-DMA', 'Distance from 50-DMA', 'Range Compression', 'Signal']].copy()
            buy_zone_display = buy_zone_display.rename(columns={
                'Status': '',
                'Range Compression': 'Compression'
            })

            st.dataframe(
                buy_zone_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Ticker": st.column_config.TextColumn(width="small"),
                    "": st.column_config.TextColumn(width="small"),
                    "Current Price": st.column_config.TextColumn(width="medium"),
                    "50-DMA": st.column_config.TextColumn(width="medium"),
                    "Distance from 50-DMA": st.column_config.TextColumn(width="medium"),
                    "Compression": st.column_config.TextColumn(width="small"),
                    "Signal": st.column_config.TextColumn(width="large"),
                }
            )

            # Charts for buy zone stocks
            col1, col2 = st.columns(2)

            with col1:
                buy_zone_chart = buy_zone_stocks.sort_values('Distance_Value', ascending=True)
                fig = go.Figure(data=[
                    go.Bar(
                        x=buy_zone_chart['Ticker'],
                        y=buy_zone_chart['Distance_Value'],
                        marker=dict(
                            color=buy_zone_chart['Distance_Value'],
                            colorscale='RdYlGn_r',
                            cmin=-3,
                            cmax=3,
                            showscale=False
                        ),
                        text=buy_zone_chart['Distance_Value'].apply(lambda x: f"{x:+.2f}%"),
                        textposition='auto'
                    )
                ])
                fig.update_layout(
                    title="Distance from 50-DMA (Buy Zone)",
                    xaxis_title="Ticker",
                    yaxis_title="Distance (%)",
                    height=400,
                    showlegend=False,
                    hovermode='x unified'
                )
                fig.add_hline(y=3, line_dash="dash", line_color="red", annotation_text="3% threshold", annotation_position="right")
                fig.add_hline(y=-3, line_dash="dash", line_color="red", annotation_text="-3% threshold", annotation_position="right")
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                fig2 = go.Figure(data=[
                    go.Bar(
                        x=buy_zone_stocks['Ticker'],
                        y=buy_zone_stocks['Range_Value'],
                        marker=dict(color='#1f77b4'),
                        text=buy_zone_stocks['Range_Value'].apply(lambda x: f"{x:.1f}%"),
                        textposition='auto'
                    )
                ])
                fig2.update_layout(
                    title="Range Compression (Buy Zone)",
                    xaxis_title="Ticker",
                    yaxis_title="Compression (%)",
                    height=400,
                    showlegend=False,
                    hovermode='x unified'
                )
                fig2.add_hline(y=30, line_dash="dash", line_color="orange", annotation_text="VCP threshold", annotation_position="right")
                st.plotly_chart(fig2, use_container_width=True)

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
            _, sectors, sub_sectors = fetch_tickers_with_sectors()
            display_sector_subsector_breakdown(df, sectors, sub_sectors)

        st.divider()

        # All stocks with filtering
        with st.expander("📊 View All Stocks", expanded=False):
            st.subheader("All Stocks Analysis")

            col1, col2, col3 = st.columns(3)

            with col1:
                show_buy_zone = st.checkbox("Buy Zone Only", value=False)

            with col2:
                sort_by = st.selectbox("Sort by", ["Ticker", "Distance from 50-DMA", "Range Compression"])

            with col3:
                search = st.text_input("Search ticker", "")

            display_df = df.copy()

            if show_buy_zone:
                display_df = display_df[display_df['Buy Zone'] == True]

            if search:
                display_df = display_df[display_df['Ticker'].str.contains(search.upper())]

            if sort_by == "Distance from 50-DMA":
                display_df = display_df.sort_values('Distance_Value', ascending=True)
            elif sort_by == "Range Compression":
                display_df = display_df.sort_values('Range_Value', ascending=True)
            else:
                display_df = display_df.sort_values('Ticker')

            display_cols = display_df[['Ticker', 'Status', 'Current Price', '50-DMA', 'Distance from 50-DMA', 'Range Compression', 'Signal']]
            display_cols = display_cols.rename(columns={'Status': '', 'Range Compression': 'Compression'})

            st.dataframe(display_cols, use_container_width=True, hide_index=True)

            csv = display_df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"stock_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

    st.divider()
    st.markdown(f"""
    <div style="text-align: center; color: #666; font-size: 12px; margin-top: 2rem;">
        <p>📈 Stock Buy Zone Analyzer | Logged in as: {st.session_state.user_name}</p>
        <p>Data from Yahoo Finance | Google Sheets Integration</p>
    </div>
    """, unsafe_allow_html=True)
