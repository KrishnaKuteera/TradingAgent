"""FMP (Financial Modeling Prep) API client.

Used for company descriptions and sector data.
Price history still comes from yfinance (different Yahoo endpoint, works on cloud).

API key priority: FMP_API_KEY env var → st.secrets["fmp"]["api_key"]
"""

import os
import requests
from typing import Optional

_BASE = "https://financialmodelingprep.com/api/v3"

# TSX symbols: Questrade uses symbol.TO but FMP needs symbol.TO too — test first,
# fall back to stripping .TO if not found.
_FMP_TICKER_MAP = {
    "CGL.C.TO": "CGL-C.TO",
    "VFV.TO":   "VFV.TO",
    "VIU.TO":   "VIU.TO",
}


def _api_key() -> Optional[str]:
    key = os.environ.get("FMP_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("fmp", {}).get("api_key")
    except Exception:
        return None


def _fmp_symbol(sym: str) -> str:
    return _FMP_TICKER_MAP.get(sym, sym)


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
    # FMP batch: up to ~50 symbols per call
    for i in range(0, len(fmp_syms), 50):
        batch = fmp_syms[i:i + 50]
        url = f"{_BASE}/profile/{','.join(batch)}"
        try:
            resp = requests.get(url, params={"apikey": key}, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            if not isinstance(data, list):
                continue
            for item in data:
                fmp_sym = item.get("symbol", "")
                orig    = sym_map.get(fmp_sym, fmp_sym)
                result[orig] = {
                    "name":     item.get("companyName") or orig,
                    "sector":   item.get("sector")   or "",
                    "industry": item.get("industry") or "",
                }
        except Exception:
            continue

    return result
