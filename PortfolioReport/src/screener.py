"""Shared CAN SLIM screener for watchlist stocks.

Used by dashboard.py (Google Sheets watchlist) and any future page that needs
to screen a list of tickers against L/S/M/N criteria.

Price data: yfinance download() — works on Streamlit Cloud (not blocked).
Sector data: FMP profiles — replaces yfinance .info which IS blocked on cloud.
"""

from datetime import datetime, timedelta
from typing import Optional
import yfinance as yf
import pandas as pd


def _safe_scalar(val) -> float:
    try:
        if hasattr(val, "item"):
            return float(val.item())
        return float(val)
    except Exception:
        return 0.0


def _rs_ratings(tickers: list, spy_return: float) -> dict[str, int]:
    """Compute relative strength rank (1–99) for each ticker vs SPY."""
    end = datetime.now()
    start = end - timedelta(days=365)
    raw: dict[str, float] = {}
    for ticker in tickers:
        try:
            data = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if len(data) == 0:
                raw[ticker] = 0.0
                continue
            ret = (_safe_scalar(data["Close"].iloc[-1]) - _safe_scalar(data["Close"].iloc[0])) / max(_safe_scalar(data["Close"].iloc[0]), 0.01) * 100
            raw[ticker] = ret
        except Exception:
            raw[ticker] = 0.0

    if not raw:
        return {}
    sorted_items = sorted(raw.items(), key=lambda x: x[1], reverse=True)
    n = len(sorted_items)
    return {ticker: int((i / n) * 99) + 1 for i, (ticker, _) in enumerate(sorted_items)}


def run_canslim_screen(tickers: list, status_callback=None) -> list[dict]:
    """Screen a list of tickers against L/S/M/N CAN SLIM criteria.

    Returns a list of dicts with keys:
        ticker, price, rs, vol_surge, above_200dma, near_pivot,
        high_52w_pct, canslim_letters, score, buy_zone,
        sector, industry, name
    """
    if not tickers:
        return []

    # Download SPY once for RS calculation
    end = datetime.now()
    start_1y = end - timedelta(days=365)
    try:
        spy_data = yf.download("SPY", start=start_1y, end=end, progress=False, auto_adjust=True)
        spy_return = (
            (_safe_scalar(spy_data["Close"].iloc[-1]) - _safe_scalar(spy_data["Close"].iloc[0]))
            / max(_safe_scalar(spy_data["Close"].iloc[0]), 0.01) * 100
        )
    except Exception:
        spy_return = 10.0

    if status_callback:
        status_callback("Calculating RS ratings…")
    rs_rank = _rs_ratings(tickers, spy_return)

    # Fetch FMP profiles for sector data
    try:
        from .fmp import fetch_profiles
        profiles = fetch_profiles(tickers)
    except Exception:
        profiles = {}

    results = []
    start_252 = end - timedelta(days=252)

    for i, ticker in enumerate(tickers):
        if status_callback:
            status_callback(f"Analyzing {ticker} ({i+1}/{len(tickers)})…")
        try:
            data = yf.download(ticker, start=start_252, end=end, progress=False, auto_adjust=True)
            if len(data) < 20:
                raise ValueError("insufficient data")

            price     = _safe_scalar(data["Close"].iloc[-1])
            sma_50    = _safe_scalar(data["Close"].tail(50).mean())
            sma_200   = _safe_scalar(data["Close"].tail(200).mean()) if len(data) >= 200 else sma_50
            high_52w  = _safe_scalar(data["High"].tail(252).max())
            pivot_high = _safe_scalar(data["High"].tail(10).max())
            vol_today = _safe_scalar(data["Volume"].iloc[-1])
            vol_avg50 = _safe_scalar(data["Volume"].tail(50).mean())

            rs_val     = rs_rank.get(ticker, 50)
            above_200  = price > sma_200
            vol_surge  = vol_today > (vol_avg50 * 1.5) if vol_avg50 > 0 else False
            near_pivot = price > pivot_high or ((high_52w - price) / high_52w * 100 < 10 if high_52w > 0 else False)
            high_52w_pct = (high_52w - price) / high_52w * 100 if high_52w > 0 else 0.0

            letters = []
            if rs_val > 70:        letters.append("L")
            if vol_surge:          letters.append("S")
            if above_200:          letters.append("M")
            if near_pivot:         letters.append("N")

            score    = len(letters)
            buy_zone = score >= 3

            prof = profiles.get(ticker, {})
            results.append({
                "ticker":         ticker,
                "price":          price,
                "rs":             rs_val,
                "vol_surge":      vol_surge,
                "above_200dma":   above_200,
                "near_pivot":     near_pivot,
                "high_52w_pct":   round(high_52w_pct, 1),
                "canslim_letters": " ".join(letters) if letters else "—",
                "score":          score,
                "buy_zone":       buy_zone,
                "name":           prof.get("name", ticker),
                "sector":         prof.get("sector", "Unknown"),
                "industry":       prof.get("industry", "Unknown"),
            })
        except Exception:
            results.append({
                "ticker": ticker, "price": 0.0, "rs": 0, "vol_surge": False,
                "above_200dma": False, "near_pivot": False, "high_52w_pct": 0.0,
                "canslim_letters": "—", "score": 0, "buy_zone": False,
                "name": ticker, "sector": "Unknown", "industry": "Unknown",
            })

    return results


def to_dataframe(results: list[dict]) -> pd.DataFrame:
    """Convert screener results to a display-ready DataFrame."""
    rows = []
    for r in results:
        rows.append({
            "Match":      "✅" if r["buy_zone"] else "❌",
            "Ticker":     r["ticker"],
            "Name":       r["name"],
            "Sector":     r["sector"],
            "Industry":   r["industry"],
            "Price":      f"${r['price']:.2f}" if r["price"] else "N/A",
            "RS":         r["rs"],
            "L":          "✅" if r["rs"] > 70 else "❌",
            "S":          "✅" if r["vol_surge"] else "❌",
            "M":          "✅" if r["above_200dma"] else "❌",
            "N":          "✅" if r["near_pivot"] else "❌",
            "CANSLIM":    r["canslim_letters"],
            "Score":      r["score"],
            "52W High %": f"{r['high_52w_pct']:.1f}%",
        })
    return pd.DataFrame(rows)
