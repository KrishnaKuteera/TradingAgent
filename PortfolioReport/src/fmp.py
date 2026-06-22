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


def fetch_earnings_growth(symbol: str) -> dict:
    """Fetch C and A data: quarterly EPS growth, acceleration, and 3-yr annual EPS growth.

    Returns dict with keys:
      c_eps_growth (% vs year ago), c_rev_growth, c_accelerating (bool),
      c_eps_current, c_eps_prior, c_quarter,
      a_eps_growth_3yr, a_roe, a_eps_years
    Falls back to yfinance income_stmt if FMP fails.
    """
    key = _api_key()
    result = {
        "c_eps_growth": None, "c_rev_growth": None,
        "c_eps_current": None, "c_eps_prior": None, "c_quarter": None,
        "c_qtr_growths": [], "c_qtr_labels": [],
        "c_accelerating": False, "c_accel_full": False,
        "a_eps_growth_3yr": None, "a_roe": None, "a_eps_years": [],
    }

    fmp_sym = _fmp_symbol(symbol)

    if key:
        try:
            # Quarterly income statement (get last 8 quarters)
            r = requests.get(f"{_BASE}/income-statement", params={
                "symbol": fmp_sym, "period": "quarter", "limit": 8, "apikey": key,
            }, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) >= 5:
                    cur_q  = data[0]
                    yago_q = data[4]  # same quarter last year
                    eps_cur  = cur_q.get("eps", 0) or 0
                    eps_prior = yago_q.get("eps", 0) or 0
                    rev_cur  = cur_q.get("revenue", 0) or 0
                    rev_prior = yago_q.get("revenue", 0) or 0

                    if eps_prior != 0:
                        result["c_eps_growth"] = (eps_cur - eps_prior) / abs(eps_prior) * 100
                    if rev_prior != 0:
                        result["c_rev_growth"] = (rev_cur - rev_prior) / abs(rev_prior) * 100
                    result["c_eps_current"] = eps_cur
                    result["c_eps_prior"]   = eps_prior
                    result["c_quarter"]     = cur_q.get("date", "")[:7]

                    # Acceleration: compute YoY growth rate for each of last 4 quarters
                    # data[0] vs data[4] = Q0, data[1] vs data[5] = Q-1, etc.
                    qtr_growths = []
                    qtr_labels  = []
                    for i in range(4):
                        if len(data) > i + 4:
                            e_cur  = data[i].get("eps", 0) or 0
                            e_prev = data[i + 4].get("eps", 0) or 0
                            if e_prev != 0:
                                g = (e_cur - e_prev) / abs(e_prev) * 100
                                qtr_growths.append(round(g, 1))
                                qtr_labels.append(data[i].get("date", "")[:7])
                    result["c_qtr_growths"] = qtr_growths   # [current, Q-1, Q-2, Q-3]
                    result["c_qtr_labels"]  = qtr_labels
                    if len(qtr_growths) >= 2:
                        result["c_accelerating"] = qtr_growths[0] > qtr_growths[1]
                    if len(qtr_growths) >= 4:
                        result["c_accel_full"] = qtr_growths[0] > qtr_growths[1] > qtr_growths[2] > qtr_growths[3]
            # Annual income statement
            r2 = requests.get(f"{_BASE}/income-statement", params={
                "symbol": fmp_sym, "period": "annual", "limit": 4, "apikey": key,
            }, timeout=15)
            if r2.status_code == 200:
                adata = r2.json()
                if isinstance(adata, list) and len(adata) >= 2:
                    eps_list = [d.get("eps", 0) or 0 for d in adata]
                    growths = []
                    for i in range(min(3, len(eps_list) - 1)):
                        if eps_list[i + 1] != 0:
                            growths.append((eps_list[i] - eps_list[i + 1]) / abs(eps_list[i + 1]) * 100)
                    if growths:
                        result["a_eps_growth_3yr"] = sum(growths) / len(growths)
                    result["a_eps_years"] = [
                        {"year": d.get("date", "")[:4], "eps": d.get("eps", 0)} for d in adata[:4]
                    ]
        except Exception:
            pass

    # Fallback: yfinance quarterly financials (works on cloud via download endpoint)
    if result["c_eps_growth"] is None:
        try:
            import yfinance as yf
            tk = yf.Ticker(symbol)
            q = tk.quarterly_income_stmt
            if q is not None and not q.empty and "Net Income" in q.index:
                ni = q.loc["Net Income"].dropna()
                if len(ni) >= 5:
                    cur_ni  = float(ni.iloc[0])
                    yago_ni = float(ni.iloc[4])
                    if yago_ni != 0:
                        result["c_eps_growth"] = (cur_ni - yago_ni) / abs(yago_ni) * 100
            a = tk.income_stmt
            if a is not None and not a.empty and "Net Income" in a.index:
                ni_a = a.loc["Net Income"].dropna()
                if len(ni_a) >= 2:
                    growths = []
                    for i in range(min(3, len(ni_a) - 1)):
                        prev = float(ni_a.iloc[i + 1])
                        if prev != 0:
                            growths.append((float(ni_a.iloc[i]) - prev) / abs(prev) * 100)
                    if growths:
                        result["a_eps_growth_3yr"] = sum(growths) / len(growths)
        except Exception:
            pass

    return result


def fetch_spy_quote() -> dict:
    """Backwards-compat alias — returns SPY quote dict."""
    quotes = fetch_market_quotes(["SPY"])
    return quotes.get("SPY", {})


def fetch_profiles(symbols: list) -> dict:
    """Fetch company name + sector + float + avgVolume for a list of symbols.

    Returns {original_symbol: {
      "name": str, "sector": str, "industry": str,
      "float": int (shares), "avgVolume": float
    }}.
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
                "name":      item.get("companyName") or orig,
                "sector":    item.get("sector")   or "",
                "industry":  item.get("industry") or "",
                "float":     item.get("sharesFloat") or 0,
                "avgVolume": item.get("avgVolume") or 0,
            }
        except Exception:
            continue

    return result


def fetch_earnings_surprise(symbol: str) -> dict:
    """Fetch earnings beat/miss data (C criterion).

    Returns dict with keys: beat_count, miss_count, avg_surprise_pct, last_surprise.
    """
    key = _api_key()
    result = {"beat_count": 0, "miss_count": 0, "avg_surprise_pct": None, "last_surprise": None}

    if not key:
        return result

    fmp_sym = _fmp_symbol(symbol)
    try:
        resp = requests.get(
            f"{_BASE}/earnings-surprises",
            params={"symbol": fmp_sym, "apikey": key},
            timeout=15,
        )
        if resp.status_code != 200:
            return result
        data = resp.json()
        if not isinstance(data, list) or not data:
            return result

        beats = sum(1 for d in data if (d.get("actualEarningsResult", 0) or 0) > (d.get("estimatedEarnings", 0) or 0))
        misses = len(data) - beats
        surprises = [d.get("surprisePercent", 0) or 0 for d in data if d.get("surprisePercent")]

        result["beat_count"] = beats
        result["miss_count"] = misses
        if surprises:
            result["avg_surprise_pct"] = sum(surprises) / len(surprises)
            result["last_surprise"] = surprises[0]
    except Exception:
        pass

    return result


def fetch_key_metrics(symbol: str) -> dict:
    """Fetch key metrics including ROE (A criterion).

    Returns dict with keys: roe, pe_ratio, debt_to_equity.
    """
    key = _api_key()
    result = {"roe": None, "pe_ratio": None, "debt_to_equity": None}

    if not key:
        return result

    fmp_sym = _fmp_symbol(symbol)
    try:
        resp = requests.get(
            f"{_BASE}/key-metrics",
            params={"symbol": fmp_sym, "limit": 1, "apikey": key},
            timeout=15,
        )
        if resp.status_code != 200:
            return result
        data = resp.json()
        if not isinstance(data, list) or not data:
            return result

        item = data[0]
        result["roe"] = item.get("returnOnEquity")
        result["pe_ratio"] = item.get("peRatio")
        result["debt_to_equity"] = item.get("debtToEquity")
    except Exception:
        pass

    return result


def fetch_earnings_calendar(symbol: str) -> Optional[str]:
    """Fetch next earnings date (for C/A context).

    Returns date string YYYY-MM-DD or None.
    """
    key = _api_key()
    if not key:
        return None

    fmp_sym = _fmp_symbol(symbol)
    try:
        resp = requests.get(
            f"{_BASE}/earnings-calendar",
            params={"symbol": fmp_sym, "apikey": key},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, list) or not data:
            return None

        # FMP returns upcoming earnings dates; take the first (nearest)
        next_date = data[0].get("date")
        return next_date if next_date else None
    except Exception:
        pass

    return None
