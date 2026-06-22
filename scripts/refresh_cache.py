"""Weekly cache refresh script.

Run locally or via GitHub Actions (see .github/workflows/refresh_earnings.yml).
Tickers come from Google Sheets "Tickers" tab (primary) + scripts/tickers.json (fallback).
Uses Claude to summarize the N (new catalyst) criterion from recent headlines.
Writes results to PortfolioReport/earnings_cache.json (committed to git).

Usage:
    python3 scripts/refresh_cache.py
    python3 scripts/refresh_cache.py --dry-run   # print output, don't write

Requires:
    ANTHROPIC_API_KEY env var (optional — skips Claude news analysis if missing)
    GCP_SERVICE_ACCOUNT_JSON env var — full service account JSON string (for Google Sheets)
      OR tradeportfolioagent-8348ccf38790.json file present locally
"""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).parent.parent
TICKERS_FILE = ROOT / "scripts" / "tickers.json"
CACHE_FILE = ROOT / "PortfolioReport" / "earnings_cache.json"

_CLAUDE_MODEL = "claude-haiku-4-5-20251001"

_N_PROMPT = """You are analyzing a stock for the CAN SLIM N criterion: does this stock have a NEW catalyst?
O'Neil defines N as: new product/service, new management, or a major new industry shift driving earnings growth.

Stock: {symbol}
Recent headlines:
{headlines}

Respond with a JSON object only (no markdown):
{{
  "catalyst_type": "new_product" | "new_service" | "new_management" | "industry_shift" | "none",
  "summary": "1-2 sentence plain-English description of the catalyst, or 'No clear new catalyst in recent news.'",
  "score": "strong" | "moderate" | "weak" | "none"
}}"""


def _fetch_yf_earnings(symbol: str) -> dict:
    result = {
        "c_eps_growth": None, "c_rev_growth": None,
        "c_eps_current": None, "c_eps_prior": None, "c_quarter": None,
        "c_qtr_growths": [], "c_qtr_labels": [], "c_qtr_eps": [],
        "c_accelerating": False, "c_accel_full": False,
        "a_eps_growth_3yr": None, "a_roe": None, "a_eps_years": [],
    }
    try:
        tk = yf.Ticker(symbol)
        q = tk.quarterly_income_stmt
        if q is not None and not q.empty:
            eps_row = next(
                (r for r in ("Basic EPS", "Diluted EPS", "Net Income") if r in q.index),
                None,
            )
            rev_row = "Total Revenue" if "Total Revenue" in q.index else None

            if eps_row:
                eps_s = q.loc[eps_row].dropna()
                rev_s = q.loc[rev_row].dropna() if rev_row else None
                labels = [str(ts)[:7] for ts in eps_s.index]

                if len(eps_s) >= 5:
                    cur = float(eps_s.iloc[0])
                    yago = float(eps_s.iloc[4])
                    if yago != 0:
                        result["c_eps_growth"] = round((cur - yago) / abs(yago) * 100, 1)
                    result["c_eps_current"] = round(cur, 2)
                    result["c_eps_prior"] = round(yago, 2)
                    result["c_quarter"] = labels[0] if labels else None

                    if rev_s is not None and len(rev_s) >= 5:
                        rc = float(rev_s.iloc[0])
                        ry = float(rev_s.iloc[4])
                        if ry != 0:
                            result["c_rev_growth"] = round((rc - ry) / abs(ry) * 100, 1)

                    qg, ql, qe = [], [], []
                    for i in range(min(4, len(eps_s) - 4)):
                        e_c = float(eps_s.iloc[i])
                        e_p = float(eps_s.iloc[i + 4])
                        if e_p != 0:
                            g = round((e_c - e_p) / abs(e_p) * 100, 1)
                            qg.append(g)
                            ql.append(labels[i] if i < len(labels) else "")
                            qe.append(round(e_c, 2))
                    result["c_qtr_growths"] = qg
                    result["c_qtr_labels"] = ql
                    result["c_qtr_eps"] = qe
                    if len(qg) >= 2:
                        result["c_accelerating"] = qg[0] > qg[1]
                    if len(qg) >= 4:
                        result["c_accel_full"] = qg[0] > qg[1] > qg[2] > qg[3]

        a = tk.income_stmt
        if a is not None and not a.empty:
            a_eps_row = next(
                (r for r in ("Basic EPS", "Diluted EPS", "Net Income") if r in a.index),
                None,
            )
            if a_eps_row:
                eps_a = a.loc[a_eps_row].dropna()
                if len(eps_a) >= 2:
                    growths = []
                    for i in range(min(3, len(eps_a) - 1)):
                        prev = float(eps_a.iloc[i + 1])
                        if prev != 0:
                            growths.append((float(eps_a.iloc[i]) - prev) / abs(prev) * 100)
                    if growths:
                        result["a_eps_growth_3yr"] = round(sum(growths) / len(growths), 1)
                    result["a_eps_years"] = [
                        {"year": str(ts)[:4], "eps": round(float(v), 2)}
                        for ts, v in zip(eps_a.index[:4], eps_a.iloc[:4])
                    ]
    except Exception:
        traceback.print_exc()

    return result


def _fetch_news_headlines(symbol: str, limit: int = 6) -> list[str]:
    try:
        tk = yf.Ticker(symbol)
        items = tk.news or []
        headlines = []
        for item in items[:limit]:
            title = item.get("content", {}).get("title", "")
            if title:
                headlines.append(title)
        return headlines
    except Exception:
        return []


def _claude_n_analysis(symbol: str, headlines: list[str]) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not headlines:
        return {"catalyst_type": "none", "summary": "No news available.", "score": "none"}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        headlines_text = "\n".join(f"- {h}" for h in headlines)
        prompt = _N_PROMPT.format(symbol=symbol, headlines=headlines_text)
        msg = client.messages.create(
            model=_CLAUDE_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        return json.loads(raw)
    except Exception:
        traceback.print_exc()
        return {"catalyst_type": "none", "summary": "Analysis failed.", "score": "none"}


def refresh_ticker(symbol: str) -> dict:
    print(f"  {symbol}...", end=" ", flush=True)
    entry = _fetch_yf_earnings(symbol)

    headlines = _fetch_news_headlines(symbol)
    entry["n_headlines"] = headlines
    entry["n_catalyst"] = _claude_n_analysis(symbol, headlines)
    entry["fetched_at"] = datetime.now(timezone.utc).isoformat()

    growth = entry.get("c_eps_growth")
    label = f"+{growth:.1f}%" if growth and growth > 0 else (f"{growth:.1f}%" if growth else "n/a")
    print(f"EPS {label}")
    return entry


def _fetch_tickers_from_sheets() -> list:
    """Read tickers from Google Sheets 'Tickers' tab.

    Credentials priority:
      1. GCP_SERVICE_ACCOUNT_JSON env var (GitHub Actions secret — full JSON string)
      2. Local service account JSON file
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly",
                  "https://www.googleapis.com/auth/drive.readonly"]

        sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
        if sa_json:
            info = json.loads(sa_json)
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        else:
            sa_file = ROOT / "tradeportfolioagent-8348ccf38790.json"
            if not sa_file.exists():
                return []
            creds = Credentials.from_service_account_file(str(sa_file), scopes=SCOPES)

        client = gspread.authorize(creds)
        ws = client.open("StockTracker").worksheet("Tickers")
        rows = ws.get_all_values()
        if not rows:
            return []
        headers = [h.lower().strip() for h in rows[0]]
        ticker_idx = headers.index("ticker") if "ticker" in headers else 0
        tickers = [
            row[ticker_idx].strip().upper()
            for row in rows[1:]
            if row and len(row) > ticker_idx and row[ticker_idx].strip()
        ]
        print(f"  Loaded {len(tickers)} tickers from Google Sheets")
        return tickers
    except Exception as e:
        print(f"  Google Sheets unavailable ({e}) — falling back to tickers.json")
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print output without writing file")
    args = parser.parse_args()

    # Primary: Google Sheets. Fallback: tickers.json
    tickers = _fetch_tickers_from_sheets()
    if not tickers:
        tickers_config = json.loads(TICKERS_FILE.read_text())
        tickers = tickers_config.get("watchlist", [])

    if not tickers:
        print("No tickers found in Google Sheets or scripts/tickers.json")
        sys.exit(1)

    # Deduplicate preserving order
    seen = set()
    tickers = [t for t in tickers if not (t in seen or seen.add(t))]

    print(f"Refreshing {len(tickers)} tickers...")
    anthropic_available = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not anthropic_available:
        print("  ANTHROPIC_API_KEY not set — skipping Claude news analysis")

    cache = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "data": {},
    }
    for sym in tickers:
        try:
            cache["data"][sym] = refresh_ticker(sym)
        except Exception as e:
            print(f"  ERROR: {sym}: {e}")

    if args.dry_run:
        print("\n--- DRY RUN OUTPUT ---")
        print(json.dumps(cache, indent=2))
    else:
        CACHE_FILE.write_text(json.dumps(cache, indent=2))
        print(f"\nWrote {CACHE_FILE}")


if __name__ == "__main__":
    main()
