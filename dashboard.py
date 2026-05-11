import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px

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

# Title and description
st.title("📈 Stock Buy Zone Analyzer")
st.markdown("""
Analyze your stock portfolio to identify **buy zone opportunities**:
- Stocks within **3% of 50-day moving average** (support levels)
- Stocks with **tight price ranges** (VCP consolidation patterns)
""")

# Sidebar configuration
st.sidebar.header("⚙️ Configuration")
refresh_button = st.sidebar.button("🔄 Run Analysis", use_container_width=True)

# Cache function for Google Sheets authentication
@st.cache_resource
def get_gspread_client():
    import json
    import os

    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

    try:
        # Try to use Streamlit secrets (for cloud deployment)
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        else:
            # Fall back to local JSON file (for local development)
            json_file = 'tradeportfolioagent-52f42fe31773.json'
            if os.path.exists(json_file):
                credentials = Credentials.from_service_account_file(json_file, scopes=SCOPES)
            else:
                st.error("❌ Service account credentials not found. Please add them to Streamlit Secrets.")
                st.stop()
    except Exception as e:
        st.error(f"❌ Authentication error: {str(e)}")
        st.stop()

    return gspread.authorize(credentials)

# Cache function for fetching tickers
@st.cache_data(ttl=3600)
def fetch_tickers():
    try:
        client = get_gspread_client()
        spreadsheet = client.open('Copy of StockTracker')
        worksheet = spreadsheet.sheet1
        all_values = worksheet.get_all_values()
        tickers = [row[0].strip().upper() for row in all_values[1:] if row and row[0].strip()]
        return tickers
    except Exception as e:
        st.error(f"Error fetching tickers from Google Sheets: {str(e)}")
        return []

# Function to analyze stocks
def analyze_stocks(tickers):
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, ticker in enumerate(tickers):
        status_text.text(f"Analyzing {ticker}... ({idx+1}/{len(tickers)})")
        progress_bar.progress((idx + 1) / len(tickers))

        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=100)

            data = yf.download(ticker, start=start_date, end=end_date, progress=False)

            if len(data) == 0:
                results.append({
                    'Ticker': ticker,
                    'Status': '⚠️ No Data',
                    'Current Price': 'N/A',
                    '50-DMA': 'N/A',
                    'Distance from 50-DMA': 'N/A',
                    'Signal': 'No Data',
                    'Buy Zone': False
                })
                continue

            current_price = data['Close'].iloc[-1].item() if hasattr(data['Close'].iloc[-1], 'item') else float(data['Close'].iloc[-1])
            sma_50 = data['Close'].tail(50).mean().item() if hasattr(data['Close'].tail(50).mean(), 'item') else float(data['Close'].tail(50).mean())

            # Calculate price range metrics
            high_52w = data['High'].tail(252).max().item() if hasattr(data['High'].tail(252).max(), 'item') else float(data['High'].tail(252).max())
            low_52w = data['Low'].tail(252).min().item() if hasattr(data['Low'].tail(252).min(), 'item') else float(data['Low'].tail(252).min())
            recent_high = data['High'].tail(20).max().item() if hasattr(data['High'].tail(20).max(), 'item') else float(data['High'].tail(20).max())
            recent_low = data['Low'].tail(20).min().item() if hasattr(data['Low'].tail(20).min(), 'item') else float(data['Low'].tail(20).min())

            distance_from_dma = ((current_price - sma_50) / sma_50) * 100

            recent_range = recent_high - recent_low
            hist_range = high_52w - low_52w
            range_compression = (recent_range / hist_range) * 100 if hist_range > 0 else 0

            is_buy_zone = False
            signals = []

            if abs(distance_from_dma) <= 3:
                is_buy_zone = True
                signals.append("📍 Within 3% of 50-DMA")

            if range_compression < 30:
                is_buy_zone = True
                signals.append("📦 Tight Range (VCP)")

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
                'Range_Value': range_compression
            })

        except Exception as e:
            results.append({
                'Ticker': ticker,
                'Status': '❌',
                'Current Price': 'Error',
                '50-DMA': 'Error',
                'Distance from 50-DMA': 'Error',
                'Signal': f'Error: {str(e)[:30]}',
                'Buy Zone': False
            })

    progress_bar.empty()
    status_text.empty()
    return results

# Main logic
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
            # Distance from 50-DMA chart
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
            # Range compression chart
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

    # All stocks with filtering
    with st.expander("📊 View All Stocks", expanded=False):
        st.subheader("All Stocks Analysis")

        # Filter options
        col1, col2, col3 = st.columns(3)

        with col1:
            show_buy_zone = st.checkbox("Buy Zone Only", value=False)

        with col2:
            sort_by = st.selectbox("Sort by", ["Ticker", "Distance from 50-DMA", "Range Compression"])

        with col3:
            search = st.text_input("Search ticker", "")

        # Filter and display
        display_df = df.copy()

        if show_buy_zone:
            display_df = display_df[display_df['Buy Zone'] == True]

        if search:
            display_df = display_df[display_df['Ticker'].str.contains(search.upper())]

        # Sort
        if sort_by == "Distance from 50-DMA":
            display_df = display_df.sort_values('Distance_Value', ascending=True)
        elif sort_by == "Range Compression":
            display_df = display_df.sort_values('Range_Value', ascending=True)
        else:
            display_df = display_df.sort_values('Ticker')

        display_cols = display_df[['Ticker', 'Status', 'Current Price', '50-DMA', 'Distance from 50-DMA', 'Range Compression', 'Signal']]
        display_cols = display_cols.rename(columns={'Status': '', 'Range Compression': 'Compression'})

        st.dataframe(display_cols, use_container_width=True, hide_index=True)

        # Download data
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"stock_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

# Footer
st.divider()
st.markdown("""
<div style="text-align: center; color: #666; font-size: 12px; margin-top: 2rem;">
    <p>📈 Stock Buy Zone Analyzer | Last Update: {}</p>
    <p>Data from Yahoo Finance | Google Sheets Integration</p>
</div>
""".format(st.session_state.get('last_update', 'Never').strftime('%Y-%m-%d %H:%M:%S') if 'last_update' in st.session_state else 'Never'),
unsafe_allow_html=True)
