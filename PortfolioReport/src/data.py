"""Data loading: Questrade API (primary) and Excel files (backup fallback)."""

import re
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

from .questrade_api import QuestradeAPI

from .config import FOLDER, CONFIG_DIR, DATA_DIR, CHANDU_ACCOUNTS, NANDU_ACCOUNTS, YF_TICKER_MAP, ETF_SYMBOLS
from .utils import safe_float, conv_cad, conv_usd, get_currency


# ---------------------------------------------------------------------------
# Excel backup (kept as fallback)
# ---------------------------------------------------------------------------

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse internal whitespace in column names (works around XLSX typos)."""
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df


def latest_file(person: str) -> Path:
    """Return the most recent activity XLSX for a given person name."""
    pattern = re.compile(
        rf"{person}QT_Activities_(\d{{2}})([A-Za-z]{{3}})(\d{{4}})\.xlsx", re.IGNORECASE
    )
    candidates = []
    for f in DATA_DIR.glob(f"{person}QT_Activities_*.xlsx"):
        m = pattern.match(f.name)
        if m:
            try:
                date = datetime.strptime(f"{m.group(1)}{m.group(2)}{m.group(3)}", "%d%b%Y")
                candidates.append((date, f))
            except ValueError:
                pass
    if not candidates:
        sys.exit(f"No {person} activity file found in {FOLDER}")
    return max(candidates, key=lambda x: x[0])[1]


def load_person(path: Path) -> dict:
    """Load all sheets from an activity XLSX into {sheet_name: DataFrame}."""
    xl = pd.ExcelFile(path)
    return {sheet: normalize_columns(xl.parse(sheet)) for sheet in xl.sheet_names}


# ---------------------------------------------------------------------------
# FX rate
# ---------------------------------------------------------------------------

def get_fx(data: dict) -> float:
    """Extract FX rate from a data dict's Balances DataFrame, fallback to 1.39095."""
    bal = data.get("Balances", pd.DataFrame())
    if not bal.empty and "FX Rate" in bal.columns:
        try:
            return float(bal["FX Rate"].dropna().iloc[0])
        except (IndexError, ValueError):
            pass
    return 1.39095


# ---------------------------------------------------------------------------
# Questrade API loaders
# ---------------------------------------------------------------------------

def _detect_asset_class(symbol: str) -> str:
    """Classify a Questrade symbol as OPT, ETF, or STK."""
    # Questrade option format: SPY17Jul26P620.00 or AAPL230120C00150000
    if re.search(r'\d{2}[A-Za-z]{3}\d{2}[PC]|\d{6}[PC]\d', symbol) or 'OPT' in symbol.upper():
        return 'OPT'
    if 'ETF' in symbol or symbol.endswith('.TO') or symbol.endswith('.CA') or symbol in ETF_SYMBOLS:
        return 'ETF'
    return 'STK'


def load_from_questrade(account_num: str, account_info: dict, person_label: str = None) -> dict:
    """Convert one Questrade account's API response to Positions + Balances DataFrames."""
    acct_type = account_info.get('info', {}).get('type', 'Unknown')

    # Derive FX rate from Questrade's own combinedBalances
    fx_rate = 1.39095
    combined = account_info.get('balances', {}).get('combinedBalances', [])
    if len(combined) >= 2:
        cad_total  = combined[0].get('totalEquity', 0)
        per_ccy    = account_info.get('balances', {}).get('perCurrencyBalances', [])
        cad_native = next((b.get('totalEquity', 0) for b in per_ccy if b.get('currency') == 'CAD'), 0)
        usd_native = next((b.get('totalEquity', 0) for b in per_ccy if b.get('currency') == 'USD'), 0)
        if cad_native > 0 and usd_native > 0:
            fx_rate = (cad_total - cad_native) / usd_native

    # --- Positions ---
    positions_list = []
    if account_info.get('positions'):
        for pos in account_info['positions'].get('positions', []):
            symbol = pos.get('symbol', '')
            if symbol.upper() in ['CAD', 'USD'] or 'DOLLAR' in symbol.upper() or 'CASH' in symbol.upper():
                continue

            mkt_val      = pos.get('currentMarketValue', 0)
            pos_currency = 'CAD' if (symbol.endswith('.TO') or symbol.endswith('.CA')) else 'USD'
            asset_class  = _detect_asset_class(symbol)

            positions_list.append({
                'Equity Symbol':      symbol,
                'Equity Description': pos.get('symbolDescription') or symbol,
                'Quantity':           pos.get('openQuantity', 0),
                'Market Value':       mkt_val,
                'Profit And Loss':    pos.get('openPnl', 0),
                'Market Price':       pos.get('currentPrice', 0),
                'Cost Per Share':     pos.get('averageEntryPrice', 0),
                'Currency':           pos_currency,
                'Account Number':     int(account_num),
                'Account':            account_num,
                'Asset Class':        asset_class,
                '_person':            person_label or 'Unknown',
            })

    positions_df = pd.DataFrame(positions_list) if positions_list else pd.DataFrame(
        columns=['Equity Symbol', 'Equity Description', 'Quantity', 'Market Value',
                 'Profit And Loss', 'Currency', 'Account']
    )

    # --- Balances ---
    cad_cash = cad_mkt = cad_equity = 0.0
    usd_cash = usd_mkt = usd_equity = 0.0
    if 'balances' in account_info:
        for bal in account_info['balances'].get('perCurrencyBalances', []):
            currency = bal.get('currency', 'CAD')
            if currency == 'CAD':
                cad_cash   += bal.get('cash', 0)
                cad_mkt    += bal.get('marketValue', 0)
                cad_equity += bal.get('totalEquity', 0)
            else:
                usd_cash   += bal.get('cash', 0)
                usd_mkt    += bal.get('marketValue', 0)
                usd_equity += bal.get('totalEquity', 0)

    eq_cad = cad_equity + (usd_equity * fx_rate)
    eq_usd = (cad_equity / fx_rate) + usd_equity

    balances_df = pd.DataFrame([{
        'Account Number':              account_num,
        'Account Type':                acct_type,
        'Cash in CAD Combined':        cad_cash + (usd_cash * fx_rate),
        'Cash in USD Combined':        (cad_cash / fx_rate) + usd_cash,
        'Market Valuein CAD Combined': cad_mkt + (usd_mkt * fx_rate),
        'Market Value in USD Combined':(cad_mkt / fx_rate) + usd_mkt,
        'Total Equity in CAD Combined':eq_cad,
        'Total Equity in USD Combined':eq_usd,
        'Cash in CAD Native':          cad_cash,
        'Cash in USD Native':          usd_cash,
        'Market Value in CAD Native':  cad_mkt,
        'Market Value in USD Native':  usd_mkt,
        'Total Equity in CAD Native':  cad_equity,
        'Total Equity in USD Native':  usd_equity,
        'FX Rate':                     fx_rate,
    }])

    return {'Positions': positions_df, 'Balances': balances_df}


def _merge_data(data: dict, new: dict) -> dict:
    """Merge a new account's data into the running aggregate."""
    if 'Positions' not in data:
        return {'Positions': new['Positions'].copy(), 'Balances': new['Balances'].copy()}
    return {
        'Positions': pd.concat([data['Positions'], new['Positions']], ignore_index=True),
        'Balances':  pd.concat([data['Balances'],  new['Balances']],  ignore_index=True),
    }


def _empty_portfolio() -> dict:
    return {
        'Positions': pd.DataFrame(columns=['Equity Symbol', 'Equity Description', 'Quantity',
                                            'Market Value', 'Profit And Loss', 'Currency']),
        'Balances':  pd.DataFrame(columns=['Currency', 'Cash', 'Market Value', 'FX Rate']),
    }


def fetch_descriptions(symbols: list) -> dict:
    """Fetch company/fund long names. Uses FMP first, falls back to cached values.

    Returns {symbol: description}.
    """
    import json
    from .fmp import fetch_profiles

    # Load existing cache (committed to repo — always readable)
    cache_path = CONFIG_DIR / "description_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    to_fetch = [s for s in symbols if s not in cache]
    if to_fetch:
        print(f"  Fetching descriptions via FMP for: {', '.join(to_fetch)}")
        profiles = fetch_profiles(to_fetch)
        for sym in to_fetch:
            cache[sym] = profiles.get(sym, {}).get("name") or sym

        # Persist back — try Config/ first (works locally), /tmp/ on cloud
        for candidate in [cache_path, Path("/tmp/description_cache.json")]:
            try:
                candidate.write_text(json.dumps(cache, indent=2))
                break
            except Exception:
                continue

    return cache


def _apply_descriptions(data: dict, desc_map: dict) -> None:
    """Overwrite Equity Description in-place where it still equals the symbol."""
    pos = data.get("Positions", pd.DataFrame())
    if pos.empty or "Equity Symbol" not in pos.columns:
        return
    def _fix(row):
        sym = str(row["Equity Symbol"]).strip()
        if row["Equity Description"] == sym:
            return desc_map.get(sym, sym)
        return row["Equity Description"]
    data["Positions"]["Equity Description"] = pos.apply(_fix, axis=1)


def _resolve_token(name: str) -> Path:
    """Return path to a token file — Config/ locally, /tmp/ on Streamlit Cloud."""
    local = CONFIG_DIR / name
    if local.exists() and local.stat().st_size > 0:
        return local
    return Path("/tmp") / name


# ---------------------------------------------------------------------------
# Portfolio snapshot cache (fallback when API is unreachable)
# ---------------------------------------------------------------------------

_SNAPSHOT_FILENAME = "portfolio_snapshot.json"


def _snapshot_path() -> Path:
    return CONFIG_DIR / _SNAPSHOT_FILENAME if CONFIG_DIR.exists() else Path("/tmp") / _SNAPSHOT_FILENAME


def _save_snapshot(chandu_data: dict, nandu_data: dict) -> None:
    import json
    snapshot = {}
    for label, data in [("chandu", chandu_data), ("nandu", nandu_data)]:
        snapshot[label] = {
            "Positions": data["Positions"].to_dict(orient="records") if not data["Positions"].empty else [],
            "Balances":  data["Balances"].to_dict(orient="records")  if not data["Balances"].empty  else [],
            "as_of":     datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    try:
        _snapshot_path().write_text(json.dumps(snapshot))
    except Exception as e:
        print(f"Warning: Could not save portfolio snapshot: {e}")


def _load_snapshot() -> tuple:
    """Load last saved snapshot. Returns (chandu_data, nandu_data, as_of_str) or None."""
    import json
    path = _snapshot_path()
    if not path.exists():
        return None
    try:
        snapshot = json.loads(path.read_text())
        result = {}
        for label in ("chandu", "nandu"):
            entry = snapshot.get(label, {})
            result[label] = {
                "Positions": pd.DataFrame(entry.get("Positions", [])),
                "Balances":  pd.DataFrame(entry.get("Balances",  [])),
            }
        as_of = snapshot.get("chandu", {}).get("as_of", "unknown time")
        return result["chandu"], result["nandu"], as_of
    except Exception as e:
        print(f"Warning: Could not read portfolio snapshot: {e}")
        return None


def load_all_from_questrade() -> tuple:
    """Fetch all account data from Questrade.

    Returns (chandu_data, nandu_data, errors).
    errors is a list of (person, message) tuples for any fetch failures.
    If the API is unreachable, falls back to the last saved snapshot.
    """
    chandu_data: dict = {}
    nandu_data:  dict = {}
    errors: list = []

    # Chandu
    try:
        print("Fetching Chandu's accounts from Questrade API...")
        api      = QuestradeAPI(refresh_token_file=str(_resolve_token("ChanduAPITracker")))
        all_data = api.get_all_data()
        for acct_num, acct_data in all_data.items():
            if acct_num in CHANDU_ACCOUNTS:
                chandu_data = _merge_data(chandu_data,
                                          load_from_questrade(acct_num, acct_data, person_label='Chandu'))
    except FileNotFoundError:
        msg = "ChanduAPITracker token file not found"
        print(f"Warning: {msg}")
        errors.append(("Chandu", msg))
    except Exception as e:
        msg = str(e)
        print(f"Warning: Could not fetch Chandu's data: {msg}")
        errors.append(("Chandu", msg))

    # Nandu
    nandu_token = _resolve_token("NanduAPITracker")
    if nandu_token.exists() and nandu_token.stat().st_size > 0:
        try:
            print("Fetching Nandu's accounts from Questrade API...")
            api      = QuestradeAPI(refresh_token_file=str(nandu_token))
            all_data = api.get_all_data()
            for acct_num, acct_data in all_data.items():
                if acct_num in NANDU_ACCOUNTS:
                    nandu_data = _merge_data(nandu_data,
                                             load_from_questrade(acct_num, acct_data, person_label='Nandu'))
        except Exception as e:
            msg = str(e)
            print(f"Warning: Could not fetch Nandu's data: {msg}")
            errors.append(("Nandu", msg))
    else:
        print("NanduAPITracker not configured, skipping Nandu's data")
        errors.append(("Nandu", "NanduAPITracker not configured — add Nandu's Questrade refresh token to enable"))

    # If API failed for everyone, try snapshot fallback
    api_failed_persons = {p for p, _ in errors}
    if "Chandu" in api_failed_persons and not chandu_data:
        cached = _load_snapshot()
        if cached:
            chandu_fallback, nandu_fallback, as_of = cached
            print(f"Using cached snapshot from {as_of}")
            chandu_data = chandu_fallback
            nandu_data  = nandu_data or nandu_fallback
            errors.append(("__stale__", as_of))
        else:
            chandu_data = _empty_portfolio()

    chandu_data = chandu_data or _empty_portfolio()
    nandu_data  = nandu_data  or _empty_portfolio()

    # Enrich descriptions from yfinance where Questrade returned null
    all_symbols = []
    for data in [chandu_data, nandu_data]:
        pos = data.get("Positions", pd.DataFrame())
        if not pos.empty and "Equity Symbol" in pos.columns:
            all_symbols += pos["Equity Symbol"].dropna().astype(str).tolist()
    if all_symbols:
        print("Fetching descriptions from yfinance...")
        desc_map = fetch_descriptions(list(set(all_symbols)))
        _apply_descriptions(chandu_data, desc_map)
        _apply_descriptions(nandu_data,  desc_map)

    # Save snapshot only after a fully live fetch (no auth errors)
    if not api_failed_persons or api_failed_persons == {"Nandu"}:
        _save_snapshot(chandu_data, nandu_data)

    return chandu_data, nandu_data, errors


# ---------------------------------------------------------------------------
# yfinance live-price updater (backup — not used when Questrade API is live)
# ---------------------------------------------------------------------------

def fetch_live_prices(symbols: list) -> dict:
    """Fetch current prices from yfinance. Returns {symbol: price}."""
    prices = {}
    if not symbols:
        return prices
    print(f"Fetching live prices for {len(symbols)} symbols...", file=sys.stderr)
    for symbol in symbols:
        try:
            yf_sym = YF_TICKER_MAP.get(symbol, symbol)
            ticker = yf.Ticker(yf_sym)
            price  = ticker.info.get('currentPrice') or ticker.info.get('regularMarketPrice')
            if price:
                prices[symbol] = float(price)
            else:
                hist = ticker.history(period='1d')
                if not hist.empty:
                    prices[symbol] = float(hist['Close'].iloc[-1])
        except Exception as e:
            print(f"  Warning: Could not fetch price for {symbol}: {e}", file=sys.stderr)
    print(f"  Fetched {len(prices)} prices", file=sys.stderr)
    return prices


def update_positions_with_live_prices(df: pd.DataFrame, live_prices: dict,
                                       fx: float, currency_overrides: dict = None) -> pd.DataFrame:
    """Overwrite Market Price/Value/P&L with yfinance live prices (backup path)."""
    if df.empty or not live_prices:
        return df
    if currency_overrides is None:
        currency_overrides = {}
    df = df.copy()
    for idx, row in df.iterrows():
        symbol = str(row.get('Equity Symbol', ''))
        if symbol not in live_prices:
            continue
        live_price        = live_prices[symbol]
        questrade_ccy     = str(row.get('Currency', 'CAD'))
        stock_ccy         = get_currency(symbol, questrade_ccy, currency_overrides)
        qty               = safe_float(row.get('Quantity', 0)) or 0.0
        cost_per_share_raw = safe_float(row.get('Cost Per Share', 0)) or 0.0

        if questrade_ccy == 'CAD' and stock_ccy == 'USD':
            cost_per_share = cost_per_share_raw
        elif questrade_ccy == 'USD' and stock_ccy == 'CAD':
            cost_per_share = cost_per_share_raw * fx
        else:
            cost_per_share = cost_per_share_raw

        df.at[idx, 'Market Price']     = live_price
        df.at[idx, 'Market Value']     = live_price * qty
        df.at[idx, 'Profit And Loss']  = (live_price - cost_per_share) * qty
        df.at[idx, 'Cost Per Share']   = cost_per_share
    return df
