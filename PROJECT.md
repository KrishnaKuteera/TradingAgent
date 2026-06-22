# TradeAgent — Project Reference

## ⚡ Start here (new session)

**This is a Streamlit app** for CAN SLIM stock analysis — a watchlist dashboard for friends
and a private portfolio page for Nanda (connected to Questrade).

**GitHub repo:** `https://github.com/KrishnaKuteera/TradingAgent.git`  
**Live app:** `https://greencandlecult.streamlit.app`  
**Streamlit auto-deploys** every time you push to `main` — no manual deploy step needed.

### The only folder that matters
```
/Users/nandakumar/Documents/Nanda_Investment/TradeAgent/
```
This is the git repo. **All code changes happen here.** Push from here.

```bash
# Standard workflow — always from this directory:
cd /Users/nandakumar/Documents/Nanda_Investment/TradeAgent
# ... make changes ...
git add <files>
git commit -m "description"
git push
# → Streamlit Cloud picks it up automatically within ~30 seconds
```

Everything else under `Nanda_Investment/` is either archived or gitignored local data.

---

## Folder Structure

```
Nanda_Investment/
├── TradeAgent/                           ← git repo = GitHub = Streamlit Cloud
│   ├── dashboard.py                      ← Streamlit main page (watchlist for friends)
│   ├── pages/
│   │   ├── 2_MyPortfolio.py              ← Questrade portfolio viewer (Nanda only)
│   │   └── 3_Portfolio_Analysis_Actions.py ← CAN SLIM analysis on live holdings
│   ├── src/
│   │   └── rules_sheet.py                ← loads O'Neil rules from Google Sheets
│   ├── PortfolioReport/                  ← shared engine used by all pages
│   │   ├── generate_report.py            ← run locally to generate HTML report
│   │   ├── PROJECT_QUESTRADE.md          ← this file
│   │   ├── src/                          ← ALL shared code lives here
│   │   │   ├── ui.py                     ← Streamlit UI components (tables, detail view)
│   │   │   ├── signals.py                ← O'Neil 46-rule evaluation engine
│   │   │   ├── fmp.py                    ← FMP API client (earnings, news, profiles)
│   │   │   ├── screener.py               ← CAN SLIM screener
│   │   │   ├── data.py                   ← Questrade API loaders
│   │   │   ├── questrade_api.py          ← Questrade OAuth client
│   │   │   ├── calc.py                   ← sector allocation, P&L helpers
│   │   │   ├── config.py                 ← paths and constants
│   │   │   ├── utils.py                  ← formatting helpers
│   │   │   └── report.py                 ← HTML report builder
│   │   ├── Config/                       ← ⚠️ gitignored — local secrets only
│   │   │   ├── ChanduAPITracker          ← Chandu's live Questrade token
│   │   │   ├── NanduAPITracker           ← Nandu's live Questrade token
│   │   │   ├── FMP_Api.rtf               ← FMP API key
│   │   │   ├── GitHub_GIST_Token.rtf     ← GitHub Gist token (token sync)
│   │   │   ├── sector_overrides.json     ← manual sector corrections (in git)
│   │   │   ├── subsector_mapping.json    ← symbol → subsector label (in git)
│   │   │   ├── currency_overrides.json   ← Questrade currency fixes (in git)
│   │   │   ├── sector_cache.json         ← yfinance cache (in git)
│   │   │   └── description_cache.json    ← yfinance cache (in git)
│   │   ├── Data/                         ← gitignored — Excel activity backups
│   │   └── Reports/                      ← gitignored — generated HTML reports
│   └── .gitignore                        ← blocks tokens, *.rtf, Data/, Reports/
│
└── Archive/
    └── PortfolioReport_old/              ← stale copy, ignore completely
```

### What is in git vs local only

| In GitHub | Local only (gitignored) |
|-----------|------------------------|
| All `src/` code | `ChanduAPITracker`, `NanduAPITracker` |
| `sector_overrides.json` | `FMP_Api.rtf`, `GitHub_GIST_Token.rtf` |
| `subsector_mapping.json` | `portfolio_snapshot.json` |
| `currency_overrides.json` | `Data/` folder (Excel files) |
| `sector_cache.json` | `Reports/` folder (HTML reports) |
| `PROJECT_QUESTRADE.md` | |

---

## App Architecture

### Two distinct features sharing the same engine

| Feature | File | Who sees it | Data source |
|---------|------|-------------|-------------|
| Watchlist dashboard | `dashboard.py` | All logged-in users | Google Sheets "Tickers" tab |
| Portfolio analysis | `pages/3_Portfolio_Analysis_Actions.py` | Nanda only | Live Questrade API |

Both use the **same 46-rule O'Neil engine** in `src/signals.py`:
- Watchlist: `run_signals_watchlist(tickers, rules)` — synthetic positions (cost=0)
- Portfolio: `run_signals(chandu_data, nandu_data, rules)` — real Questrade positions

Both render using **shared UI components** in `src/ui.py` — any fix applies to both.

### O'Neil rules

Rules live in Google Sheets ("TradingRules" tab in "StockTracker" spreadsheet).  
`src/rules_sheet.py` reads them via gspread. The dashboard shows them read-only;
the portfolio page lets Nanda edit thresholds which save back to Sheets.

### Data sources

| Source | What it provides | Notes |
|--------|-----------------|-------|
| **yfinance `download()`** | 1-yr daily OHLCV per symbol | Works on Streamlit Cloud |
| **FMP `/stable/`** | Earnings, news, profiles, sector | Free tier; key in `FMP_Api.rtf` / Streamlit secrets |
| **Questrade API** | Live positions, balances, market values | Token rotates on every call |
| **Google Sheets** | Watchlist tickers, O'Neil rules, user auth | Via gspread + service account |

---

## Account Mapping

**Chandu's Accounts:**
- RESP (52854708)
- Spousal RRSP (53224816)
- RRSP (53417370)
- TFSA (53718281)

**Nandu's Accounts:**
- Margin (29232920)
- RRSP (53076602)
- TFSA (53718191)

---

## Streamlit Cloud Setup

App is deployed from `main` branch of `KrishnaKuteera/TradingAgent`.

### Secrets required (Streamlit Cloud → App → Settings → Secrets)

```toml
[questrade]
chandu_token = "<current refresh token>"
nandu_token  = "<current refresh token>"

[fmp]
api_key = "<FMP API key>"

[google]
sheet_url = "<full Google Sheets URL for TradingRules>"

[gcp_service_account]
# full service account JSON for Google Sheets access
type = "service_account"
project_id = "..."
# etc.
```

### Writable paths on Cloud
Only `/tmp/` is writable. Caches and tokens fall back automatically:
- `Config/ChanduAPITracker` → `/tmp/ChanduAPITracker`
- `sector_cache.json` → `/tmp/sector_cache.json`

---

## ⚠️ Questrade Token Rotation

Questrade refresh tokens are **single-use** — they rotate on every API call.

**Problem:** If you run `generate_report.py` locally, the local token updates but
Streamlit Cloud still has the old (dead) token → `Authentication failed: Bad Request`.

**Rule:** Only use from one place at a time. If you run locally, update the cloud secret.

**To fix after local run:**
1. `cat TradeAgent/PortfolioReport/Config/ChanduAPITracker` — copy the new token
2. Streamlit Cloud → App → ⋮ → Settings → Secrets → update `chandu_token`
3. Save → app reboots automatically

**Permanent fix (future):** Store live token in GCP Secret Manager or Firestore so
both local and cloud always read/write from the same place.

---

## Setting Up on a New Laptop

Everything in GitHub comes down automatically. The only manual step is restoring the secrets that are intentionally NOT in GitHub.

### Step 1 — Clone the repo
```bash
cd ~/Documents
mkdir Nanda_Investment && cd Nanda_Investment
git clone https://github.com/KrishnaKuteera/TradingAgent.git
```

### Step 2 — Restore secrets (copy from old laptop or original source)

These files are gitignored and must be placed manually:

| File | Destination | Where to get it |
|------|-------------|----------------|
| `ChanduAPITracker` | `TradeAgent/PortfolioReport/Config/` | Copy from old laptop |
| `NanduAPITracker` | `TradeAgent/PortfolioReport/Config/` | Copy from old laptop |
| `FMP_Api.rtf` | `TradeAgent/PortfolioReport/Config/` | Copy from old laptop |
| `GitHub_GIST_Token.rtf` | `TradeAgent/PortfolioReport/Config/` | Copy from old laptop |
| `tradeportfolioagent-8348ccf38790.json` | `TradeAgent/` | Google Cloud Console → IAM → Service Accounts → download key |

### Step 3 — Install dependencies
```bash
cd TradeAgent
pip install -r requirements.txt
```

### Step 4 — Verify
```bash
python3 PortfolioReport/generate_report.py
```

**Streamlit Cloud is unaffected** — it runs from GitHub directly, not your laptop.
The live app at `greencandlecult.streamlit.app` keeps running even if your laptop is off or wiped.

---

## Running the HTML Report Locally

```bash
cd /Users/nandakumar/Documents/Nanda_Investment/TradeAgent
python3 PortfolioReport/generate_report.py
```

Output: `PortfolioReport/Reports/PortfolioReport_DDMMYYYY.html`

---

## How the Signals Engine Works

1. `fetch_technicals(symbols)` — downloads 1yr OHLCV via yfinance, computes:
   SMA50, SMA200, RS rating, distribution days, consecutive down days, vol ratio, etc.
2. `evaluate_position(pos, rules, tech)` — runs all enabled rules against one position
3. Each rule returns `{status, value, action, urgency, detail}`  
   Status ∈ `PASS / FAIL / WARN / N/A`
4. `_verdict()` in `ui.py` aggregates rule results → `buy / sell / watch / hold / monitor`
5. Main table sorted by: urgency → verdict → buy score descending

### Rule categories
| Category | Description |
|----------|-------------|
| `CANSLIM` | C/A/N/S/L/I/M criteria |
| `BUY_ENTRY` | Breakout, pivot, base patterns |
| `SELL_DEFENSIVE` | Cut losses (hard stop, alt stop) |
| `SELL_OFFENSIVE` | Lock gains (climax run, take profits) |
| `POSITION` | Position sizing limits |
| `MARKET` | SPY/QQQ direction |
| `PERSONAL` | Sharan's custom rules |

---

## UI Structure (`src/ui.py`)

`render_decision_view(holdings, rules, show_account, key)` — main entry point:
- **Market banner** — SPY+QQQ status shown once at top (same for all stocks)
- **Summary table** — Stock | TradingView link | Verdict | Buy ✓ | Sell ✗ | [Account | P&L]
- **Reason callout** — colour-coded box below table for selected row (green/yellow/red)
- **Detail section** — full CAN SLIM breakdown for selected stock:
  1. CAN SLIM (C/A/N/S/L/I/M) — HTML table, wraps text
  2. Buy signals — HTML table
  3. Sell signals technical — HTML table
  4. Sell signals position — HTML table
  5. Price performance — green/red styled dataframe

Detail tables use `_html_table()` (not `st.dataframe`) so text wraps properly.  
Main summary table uses `st.dataframe` with `on_select="rerun"` for row selection.

---

## Known Issues

| # | Status | Issue |
|---|--------|-------|
| 1–7 | ✅ Fixed | Various display, auth, path bugs (see git log) |
| 8 | ⚠️ Expected | Questrade API lags web UI by minutes (`isRealTime: false`) |
| 9 | ✅ Fixed | Token rotation — GitHub Gist sync |
| 10 | ℹ️ Non-critical | Activities endpoint `startTime` error — not used |
| 11 | ✅ Fixed | Nandu's account live |
| 12 | ⚠️ Known | Main summary table Reason column can't wrap (st.dataframe iframe limitation) — shown as callout box below instead |

---

## CAN SLIM Data — What We Have vs What's Missing

### Tier 1 — Complete ✅

| Letter | Data | Source |
|--------|------|--------|
| C | Quarterly EPS YoY %, revenue growth %, acceleration trend | FMP `/income-statement` + yfinance fallback |
| A | 3-yr avg annual EPS growth %, ROE % | FMP `/income-statement` + `/key-metrics` |
| N | Latest 3 news headlines (manual review for catalyst) | FMP `/news` |
| S | Today's vol vs 50-day avg, float, avg daily volume | yfinance + FMP `/profile` |
| L | IBD-weighted RS (2× last 63d, 1× prior periods) — approximate | yfinance 1yr OHLCV |
| I | Float heuristic only (10M–500M = institutional range) | FMP `/profile` |
| M | SPY + QQQ vs 50/200-SMA, distribution day count | FMP quotes + yfinance |

### Tier 2 — Build next

| Letter | Gap | Source | Effort |
|--------|-----|--------|--------|
| I | No actual institutional holder count or QoQ change — **biggest gap** | FMP `/institutional-ownership` | Medium |
| M | SMA too basic — need Follow-Through Day (FTD) detection | yfinance SPY/QQQ daily | Medium |
| L | Industry group rank missing | FMP `/sector-performance` | Medium |
| S | Check vol on actual breakout pivot day, not today | yfinance daily OHLCV | Medium |
| C | TSX stocks may have missing/lagged earnings data | FMP coverage gap | Low |

### Tier 2 specs

**I — Institutional ownership**
- `FMP /institutional-ownership?symbol=X` → quarterly holder count + % owned
- Compare current vs prior quarter → ✅ rising / ⚠️ flat / ❌ falling

**M — Follow-Through Day (FTD)**  
O'Neil's exact confirmed-uptrend definition:
1. Find most recent market low (closing low)
2. Day 1 = any up-close day after that low
3. FTD = Day 4+ where index up ≥ 1.25% on higher vol than prior session
4. Invalidated if index undercuts Day 1 low
- Data: `yfinance download("SPY QQQ", period="3mo")` — already downloaded

**L — Industry group rank**
- `FMP /sector-performance` → rank sectors by 1M + 3M return vs SPY
- Show: "Technology — Rank 2/11 sectors"

### Tier 3 — Future / manual

| Item | Notes |
|------|-------|
| N — catalyst scoring | DeepVue screenshot upload; TODO stub in `ui.py` |
| C/A/I — DeepVue | Upload screenshots to populate EPS, ROE, institutional data |
| L — IBD RS Rating | Paid IBD subscription; only if our computed RS proves inaccurate |
| S — base pattern recognition | Cup-with-handle, flat base detection from chart — complex |

---

## Next Steps

- [ ] **Tier 2 CAN SLIM** — institutional ownership (I), FTD detection (M), industry group rank (L)
- [ ] **Token rotation permanent fix** — GCP Secret Manager or Firestore
- [ ] **Auto-sync** — pre-commit hook or symlink so local edits don't need manual copy to TradeAgent
