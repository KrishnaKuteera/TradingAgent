"""Portfolio calculations: sector allocation, position consolidation, data loading."""

import json
import time
from typing import Optional

import pandas as pd
import yfinance as yf

from pathlib import Path
from .config import FOLDER, CONFIG_DIR, ACCOUNT_LABELS, YF_TICKER_MAP, SECTOR_NAMES

# On Streamlit Cloud, Config/ doesn't exist — fall back to /tmp/ for writable cache
_CFG = CONFIG_DIR if CONFIG_DIR.exists() else Path("/tmp")
from .utils import safe_float, conv_cad, get_currency


# ---------------------------------------------------------------------------
# Sector helpers
# ---------------------------------------------------------------------------

def _norm_sector(raw: str) -> str:
    key = raw.lower().replace(" ", "_").replace("-", "_")
    return SECTOR_NAMES.get(key, raw.replace("_", " ").title())


def _yfin_fetch(symbol: str) -> Optional[dict]:
    """Fetch sector weightings from yfinance. Returns {sector: weight} or None."""
    try:
        yf_sym = YF_TICKER_MAP.get(symbol, symbol)
        ticker = yf.Ticker(yf_sym)
        info   = ticker.info

        sec = info.get("sector")
        if sec:
            return {_norm_sector(sec): 1.0}

        try:
            sw = ticker.funds_data.sector_weightings
            if sw:
                weights = {_norm_sector(k): float(v) for k, v in sw.items() if v}
                total = sum(weights.values())
                if total > 0:
                    return {k: v / total for k, v in weights.items()}
        except Exception:
            pass

        sw_list = info.get("sectorWeightings")
        if sw_list:
            weights: dict = {}
            for item in (sw_list if isinstance(sw_list, list) else [sw_list]):
                for k, v in item.items():
                    s = _norm_sector(k)
                    weights[s] = weights.get(s, 0.0) + float(v or 0)
            total = sum(weights.values())
            if total > 0:
                return {k: v / total for k, v in weights.items() if v > 0}
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Data file loaders
# ---------------------------------------------------------------------------

def load_sector_data(symbols: list) -> dict:
    """Return {symbol: {sector: weight}}, fetching from yfinance for any not cached."""
    cache_path     = _CFG       / "sector_cache.json"
    overrides_path = CONFIG_DIR / "sector_overrides.json"

    cache     = json.loads(cache_path.read_text())     if cache_path.exists()     else {}
    overrides = json.loads(overrides_path.read_text()) if overrides_path.exists() else {}

    to_fetch = [
        s for s in symbols
        if s not in cache and not (s in overrides and overrides[s] is not None)
    ]
    if to_fetch:
        print(f"  Fetching sector data for: {', '.join(to_fetch)}")
        for sym in to_fetch:
            cache[sym] = _yfin_fetch(sym)
            time.sleep(0.3)
        cache_path.write_text(json.dumps(cache, indent=2))

    sector_data: dict = {}
    for sym in symbols:
        if sym in overrides and overrides[sym] is not None:
            sector_data[sym] = overrides[sym]
        elif cache.get(sym):
            sector_data[sym] = cache[sym]
    return sector_data


def load_subsector_data() -> dict:
    """Load {symbol: subsector} from subsector_mapping.json."""
    path = CONFIG_DIR / "subsector_mapping.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    subsectors = {}
    for category, mappings in data.items():
        if not category.startswith("_"):
            subsectors.update(mappings)
    return subsectors


def load_currency_overrides() -> dict:
    """Load currency overrides from currency_overrides.json."""
    path = CONFIG_DIR / "currency_overrides.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Position helpers
# ---------------------------------------------------------------------------

def get_subsector(symbol: str, subsector_data: dict, sector_data: dict) -> str:
    if symbol in subsector_data:
        return subsector_data[symbol]
    sectors = sector_data.get(symbol, {})
    if sectors:
        return "Multi-Sector" if len(sectors) > 1 else next(iter(sectors.keys()))
    return "Unknown"


def get_all_symbols(chandu_data: dict, nandu_data: dict) -> list:
    """Return sorted list of non-option, non-cash symbols across both portfolios."""
    symbols: set = set()
    for data in [chandu_data, nandu_data]:
        pos = data.get("Positions", pd.DataFrame())
        if pos.empty or "Equity Symbol" not in pos.columns:
            continue
        non_opt = pos[pos["Asset Class"].str.upper() != "OPT"] if "Asset Class" in pos.columns else pos
        for _, row in non_opt.iterrows():
            sym  = str(row.get("Equity Symbol", "")).strip()
            desc = str(row.get("Equity Description", "")).upper()
            if sym and "DOLLAR" not in desc and "CASH" not in desc:
                symbols.add(sym)
    return sorted(symbols)


def consolidate_positions(df: pd.DataFrame, person_label: str = None) -> pd.DataFrame:
    """Group same symbol across accounts, summing quantities and values."""
    if df.empty or "Asset Class" not in df.columns:
        return df.copy()

    non_opt = df[df["Asset Class"].str.upper() != "OPT"].copy()
    if non_opt.empty:
        return non_opt

    consolidated = []
    for symbol, group in non_opt.groupby("Equity Symbol"):
        accounts = []
        for _, r in group.iterrows():
            acct_num = str(int(r.get("Account Number", 0))) if pd.notna(r.get("Account Number")) else ""
            if acct_num and acct_num in ACCOUNT_LABELS:
                acct_type = ACCOUNT_LABELS[acct_num].split("(")[0].strip()
                if acct_type == "Spousal RRSP":
                    acct_type = "SRRSP"
                person   = person_label or r.get("_person", "Unknown")
                formatted = f"{person}_{acct_type}"
                if formatted not in accounts:
                    accounts.append(formatted)

        qty_sum = sum(safe_float(r.get("Quantity",        0)) or 0.0 for _, r in group.iterrows())
        mv_sum  = sum(safe_float(r.get("Market Value",    0)) or 0.0 for _, r in group.iterrows())
        pnl_sum = sum(safe_float(r.get("Profit And Loss", 0)) or 0.0 for _, r in group.iterrows())

        row = group.iloc[0].copy()
        row["Quantity"]        = qty_sum
        row["Market Value"]    = mv_sum
        row["Profit And Loss"] = pnl_sum
        row["_accounts"]       = accounts
        consolidated.append(row)

    return pd.DataFrame(consolidated)


# ---------------------------------------------------------------------------
# Allocation computation
# ---------------------------------------------------------------------------

def compute_sector_alloc(df: pd.DataFrame, sector_data: dict, fx: float,
                         balances: pd.DataFrame = None, acct_nums: list = None,
                         currency_overrides: dict = None):
    """Returns (sector_totals, unknown_tickers, total_mv_cad including cash)."""
    if currency_overrides is None:
        currency_overrides = {}
    sector_totals: dict = {}
    unknown: list = []
    total_mv = 0.0

    if not df.empty:
        for _, r in df.iterrows():
            sym       = str(r.get("Equity Symbol", "")).strip()
            ccy       = get_currency(sym, str(r.get("Currency", "CAD")), currency_overrides)
            mv_cad    = conv_cad(r.get("Market Value"), ccy, fx)
            asset_cls = str(r.get("Asset Class", "")).upper() if "Asset Class" in df.columns else ""
            total_mv += mv_cad

            if asset_cls == "OPT":
                sector_totals["Hedge"] = sector_totals.get("Hedge", 0.0) + mv_cad
                continue

            weights = sector_data.get(sym)
            if weights:
                for sector, w in weights.items():
                    sector_totals[sector] = sector_totals.get(sector, 0.0) + mv_cad * w
            else:
                sector_totals["Unknown"] = sector_totals.get("Unknown", 0.0) + mv_cad
                if sym not in unknown:
                    unknown.append(sym)

    cash_cad_equiv = _sum_cash_cad(balances, acct_nums, fx)
    total_mv += cash_cad_equiv
    if cash_cad_equiv > 0:
        sector_totals["Cash"] = sector_totals.get("Cash", 0.0) + cash_cad_equiv

    return sector_totals, unknown, total_mv


def compute_subsector_alloc(df: pd.DataFrame, sector_data: dict, subsector_data: dict,
                             fx: float, balances: pd.DataFrame = None, acct_nums: list = None,
                             currency_overrides: dict = None):
    """Returns (subsector_totals, total_mv_cad including cash)."""
    if currency_overrides is None:
        currency_overrides = {}
    subsector_totals: dict = {}
    total_mv = 0.0

    if not df.empty:
        non_opt = df[df["Asset Class"].str.upper() != "OPT"].copy() if "Asset Class" in df.columns else df.copy()
        for _, r in non_opt.iterrows():
            sym    = str(r.get("Equity Symbol", "")).strip()
            ccy    = get_currency(sym, str(r.get("Currency", "CAD")), currency_overrides)
            mv_cad = conv_cad(r.get("Market Value"), ccy, fx)
            total_mv += mv_cad
            sub = get_subsector(sym, subsector_data, sector_data)
            subsector_totals[sub] = subsector_totals.get(sub, 0.0) + mv_cad

    cash_cad_equiv = _sum_cash_cad(balances, acct_nums, fx)
    total_mv += cash_cad_equiv
    if cash_cad_equiv > 0:
        subsector_totals["Cash"] = subsector_totals.get("Cash", 0.0) + cash_cad_equiv

    return subsector_totals, total_mv


def _sum_cash_cad(balances: pd.DataFrame, acct_nums: list, fx: float) -> float:
    """Sum cash (CAD equivalent) from balances, optionally filtered by account list."""
    if balances is None or balances.empty:
        return 0.0
    total = 0.0
    for _, r in balances.iterrows():
        acct = str(int(r.get("Account Number", 0))) if pd.notna(r.get("Account Number")) else ""
        if acct_nums and acct not in acct_nums:
            continue
        cash_cad = safe_float(r.get("Cash in CAD Combined")) or 0.0
        cash_usd = safe_float(r.get("Cash in USD"))          or 0.0
        total += cash_cad + (cash_usd * fx)
    return total


# ---------------------------------------------------------------------------
# P&L helpers shared across balance tables
# ---------------------------------------------------------------------------

def calc_pnl_for_account(acct: str, positions: pd.DataFrame, fx: float,
                          currency_overrides: dict) -> tuple:
    """Returns (combined_cad_pnl, combined_usd_pnl, cad_pnl, usd_pnl) for one account."""
    combined_cad = combined_usd = cad = usd = 0.0
    if positions is None or positions.empty:
        return combined_cad, combined_usd, cad, usd

    acct_pos = positions[
        positions["Account Number"].apply(lambda x: str(int(x)) if pd.notna(x) else "") == acct
    ]
    for _, p in acct_pos.iterrows():
        p_val = safe_float(p.get("Profit And Loss")) or 0.0
        ccy   = get_currency(str(p.get("Equity Symbol", "")).strip(),
                             str(p.get("Currency", "CAD")), currency_overrides)
        p_cad = conv_cad(p_val, ccy, fx)
        p_usd = p_val if ccy.upper() == "USD" else p_cad / fx
        combined_cad += p_cad
        combined_usd += p_usd
        if ccy.upper() == "CAD":
            cad += p_cad
        else:
            usd += p_usd

    return combined_cad, combined_usd, cad, usd
