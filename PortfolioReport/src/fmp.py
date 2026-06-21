"""FMP (Financial Modeling Prep) API client.

Used for company descriptions and sector data.
Price history still comes from yfinance (different Yahoo endpoint, works on cloud).

API key priority: FMP_API_KEY env var → st.secrets["fmp"]["api_key"]
"""

import os
import requests
from typing import Optional

_BASE = "https://financialmodelingprep.com/stable"

# TSX symbols: Questrade uses symbol.TO but FMP needs symbol.TO too — test first,
# fall back to stripping .TO if not found.
_FMP_TICKER_MAP = {
    "CGL.C.TO": "CGL-C.TO",
    "VFV.TO":   "VFV.TO",
    "VIU.TO":   "VIU.TO",
}


def _api_key() -> Optional[str]:
    # 1. Environment variable
    key = os.environ.get("FMP_API_KEY")
    if key:
        return key
    # 2. Streamlit secrets (cloud)
    try:
        import streamlit as st
        k = st.secrets.get("fmp", {}).get("api_key")
        if k:
            return k
    except Exception:
        pass
    # 3. Local config file
    try:
        from .config import CONFIG_DIR
        import re
        rtf = (CONFIG_DIR / "FMP_Api.rtf").read_text()
        # Extract last word — the key is the only non-RTF token at the end
        tokens = re.findall(r'[A-Za-z0-9]{20,}', rtf)
        if tokens:
            return tokens[-1]
    except Exception:
        pass
    return None


def _fmp_symbol(sym: str) -> str:
    return _FMP_TICKER_MAP.get(sym, sym)


def fetch_market_quotes(symbols: list = None) -> dict:
    """Fetch SPY and QQQ quotes from FMP (free tier).

    Returns {symbol: {price, priceAvg50, priceAvg200, changePercentage, yearHigh, yearLow}}.
    """
    if symbols is None:
        symbols = ["SPY", "QQQ"]
    key = _api_key()
    if not key:
        return {}
    result = {}
    for sym in symbols:
        try:
            resp = requests.get(
                f"{_BASE}/quote",
                params={"symbol": sym, "apikey": key},
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            if isinstance(data, list) and data:
                result[sym] = data[0]
        except Exception:
            continue
    return result


def fetch_news(symbol: str, limit: int = 3) -> list:
    """Fetch recent news headlines for a symbol (free tier).

    Returns list of {title, publishedDate, url}.
    """
    key = _api_key()
    if not key:
        return []
    try:
        resp = requests.get(
            f"{_BASE}/news",
            params={"symbols": _fmp_symbol(symbol), "limit": limit, "apikey": key},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        if not isinstance(data, list):
            return []
        return [{"title": d.get("title", ""), "date": d.get("publishedDate", "")[:10]}
                for d in data if d.get("title")]
    except Exception:
        return []


def fetch_spy_quote() -> dict:
    """Backwards-compat alias — returns SPY quote dict."""
    quotes = fetch_market_quotes(["SPY"])
    return quotes.get("SPY", {})


def fetch_profiles(symbols: list) -> dict:
    """Fetch company name + sector for a list of symbols in one API call.

    Returns {original_symbol: {"name": str, "sector": str, "industry": str}}.
    Symbols not found are silently omitted.
    """
    key = _api_key()
    if not key:
        return {}

    # Map to FMP symbols, deduplicate
    sym_map = {_fmp_symbol(s): s for s in symbols}
    fmp_syms = list(sym_map.keys())

    result = {}
    for fmp_sym in fmp_syms:
        orig = sym_map.get(fmp_sym, fmp_sym)
        try:
            resp = requests.get(
                f"{_BASE}/profile",
                params={"symbol": fmp_sym, "apikey": key},
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            if not isinstance(data, list) or not data:
                continue
            item = data[0]
            result[orig] = {
                "name":     item.get("companyName") or orig,
                "sector":   item.get("sector")   or "",
                "industry": item.get("industry") or "",
            }
        except Exception:
            continue

    return result
