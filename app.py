import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# Authenticate with Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
credentials = Credentials.from_service_account_file(
    'tradeportfolioagent-52f42fe31773.json',
    scopes=SCOPES
)
client = gspread.authorize(credentials)

# Open the spreadsheet and get the worksheet
spreadsheet = client.open('Copy of StockTracker')
worksheet = spreadsheet.sheet1  # Gets the first sheet

# Read all ticker symbols from the sheet
all_values = worksheet.get_all_values()
tickers = [row[0].strip().upper() for row in all_values[1:] if row and row[0].strip()]  # Skip header

if not tickers:
    print("No tickers found in the sheet.")
    exit()

print(f"Found {len(tickers)} tickers to analyze: {', '.join(tickers)}\n")

# Fetch data and analyze
buy_zone_stocks = []

for ticker in tickers:
    try:
        # Get historical data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=100)

        data = yf.download(ticker, start=start_date, end=end_date, progress=False)

        if len(data) == 0:
            print(f"❌ {ticker}: No data found")
            continue

        current_price = data['Close'].iloc[-1].item() if hasattr(data['Close'].iloc[-1], 'item') else float(data['Close'].iloc[-1])
        sma_50 = data['Close'].tail(50).mean().item() if hasattr(data['Close'].tail(50).mean(), 'item') else float(data['Close'].tail(50).mean())

        # Calculate price range metrics
        high_52w = data['High'].tail(252).max().item() if hasattr(data['High'].tail(252).max(), 'item') else float(data['High'].tail(252).max())
        low_52w = data['Low'].tail(252).min().item() if hasattr(data['Low'].tail(252).min(), 'item') else float(data['Low'].tail(252).min())
        recent_high = data['High'].tail(20).max().item() if hasattr(data['High'].tail(20).max(), 'item') else float(data['High'].tail(20).max())
        recent_low = data['Low'].tail(20).min().item() if hasattr(data['Low'].tail(20).min(), 'item') else float(data['Low'].tail(20).min())

        # Distance from 50-DMA (percentage)
        distance_from_dma = ((current_price - sma_50) / sma_50) * 100

        # Tight range indicator (VCP style): recent range vs historical range
        recent_range = recent_high - recent_low
        hist_range = high_52w - low_52w
        range_compression = (recent_range / hist_range) * 100 if hist_range > 0 else 0

        is_buy_zone = False
        reasons = []

        # Check if within 3% of 50-DMA
        if abs(distance_from_dma) <= 3:
            is_buy_zone = True
            reasons.append(f"Within 3% of 50-DMA ({distance_from_dma:+.2f}%)")

        # Check for tight price range (VCP: compressed range)
        if range_compression < 30:  # Recent range is less than 30% of historical range
            is_buy_zone = True
            reasons.append(f"Tight range pattern ({range_compression:.1f}% compression)")

        if is_buy_zone:
            buy_zone_stocks.append({
                'Ticker': ticker,
                'Current Price': f"${current_price:.2f}",
                '50-DMA': f"${sma_50:.2f}",
                'Distance from 50-DMA': f"{distance_from_dma:+.2f}%",
                'Reasons': ', '.join(reasons)
            })
            print(f"✅ {ticker}: {', '.join(reasons)}")
        else:
            print(f"⭕ {ticker}: No buy signals ({distance_from_dma:+.2f}% from 50-DMA)")

    except Exception as e:
        print(f"❌ {ticker}: Error - {str(e)}")

# Print summary
print("\n" + "="*80)
print("BUY ZONE STOCKS SUMMARY")
print("="*80)

if buy_zone_stocks:
    df = pd.DataFrame(buy_zone_stocks)
    print(df.to_string(index=False))
    print(f"\n✅ Total stocks in buy zone: {len(buy_zone_stocks)} out of {len(tickers)}")
else:
    print("No stocks found in buy zone currently.")
