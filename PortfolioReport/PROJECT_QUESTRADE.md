# Questrade Portfolio Report

## Status
✅ **LIVE** — Reports generated from live Questrade API data  
✅ **Currency Display** — Holdings show native currency; balance tables have 4-view selector  
✅ **Error Banner** — HTML report shows actionable error message when API fails  
✅ **Modular Codebase** — Monolith refactored into `src/` package (5 modules)  
✅ **Streamlit Cloud** — Portfolio page live at TradeAgent app, accessible to user "Nanda" only  
✅ **Description Lookup** — yfinance fallback fills in descriptions when Questrade returns `null`  
✅ **Token Rotation** — GitHub Gist-based sync keeps local & cloud tokens in sync  
✅ **Both Accounts** — Chandu & Nandu tokens configured; both accounts report live data  
✅ **Tier 1 CAN SLIM** — Full C/A/N/S/L/M/I screening with fundamentals (EPS, ROE, earnings date, float, volume)  
⚠️ **Note** — API data may lag web UI by minutes (`"isRealTime": false`)

---

## Folder Structure

```
Nanda_Investment/
├── PortfolioReport/                      ← this project
│   ├── generate_report.py                ← entry point; run this to generate report
│   ├── PROJECT_QUESTRADE.md
│   ├── src/
│   │   ├── questrade_api.py              ← Questrade OAuth client
│   │   ├── config.py                     ← constants + folder path definitions
│   │   ├── utils.py                      ← formatting, currency conversion, HTML cell builders
│   │   ├── calc.py                       ← sector allocation, position consolidation, P&L helpers
│   │   ├── data.py                       ← Questrade API loaders + Excel backup fallback
│   │   └── report.py                     ← all HTML generation, CSS, JS, build_html()
│   ├── Config/
│   │   ├── ChanduAPITracker              ← Chandu's Questrade refresh token (sensitive)
│   │   ├── NanduAPITracker               ← Nandu's Questrade refresh token (sensitive)
│   │   ├── sector_cache.json             ← yfinance sector data cache (auto-updated)
│   │   ├── sector_overrides.json         ← manual sector corrections per symbol
│   │   ├── subsector_mapping.json        ← symbol → subsector label mapping
│   │   └── currency_overrides.json       ← correct Questrade currency misclassifications
│   ├── Data/
│   │   ├── ChanduQT_Activities_*.xlsx    ← latest Chandu activity file (Excel backup)
│   │   └── NanduQT_Activities_*.xlsx     ← latest Nandu activity file (Excel backup)
│   └── Reports/
│       └── PortfolioReport_DDMMYYYY.html ← generated HTML reports
│
├── TradeAgent/                           ← separate Streamlit trading dashboard project
└── Archive/                              ← old scripts and historical Excel files
```

### Module dependency chain (no circular imports)
`config` ← `utils` ← `calc` ← `data` ← `report` ← `generate_report`

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

## How It Works

### Data Flow
1. `generate_report.py` calls `load_all_from_questrade()` → returns `(chandu_data, nandu_data, errors)`
2. `data.py: load_from_questrade()` converts one account's API response to `Positions` + `Balances` DataFrames
   - Asset class detection via regex (`_detect_asset_class`) — handles Questrade option format `SPY17Jul26P620.00`
   - FX rate derived from Questrade's own `combinedBalances` (not hardcoded)
   - Stores both **combined** and **native** equity values for the 4-view currency toggle
3. `calc.py` consolidates positions, computes sector/subsector allocations
4. `report.py: build_html()` assembles the full HTML report
5. On any API error, `error_banner()` inserts a yellow warning div with next steps

### Market Values
- **Source:** Questrade API `currentMarketValue` — no yfinance price lookup
- **FX Rate:** Derived from `combinedBalances` (total CAD equity ÷ USD equity ≈ actual rate used by Questrade)

### Currency System (4-view)
- **Combined in CAD** — all accounts converted to CAD equivalent
- **Combined in USD** — all accounts converted to USD equivalent  
- **CAD** — CAD-native positions only, no conversion
- **USD** — USD-native positions only, no conversion
- Balance tables toggle via CSS `display:none/''` on elements with `.view-{name}` classes
- `switchView()` JS uses `data-view` attributes to update button styles (fixes duplicate-ID bug in multi-tab layout)
- Positions tables always show native currency only — no toggle

### Sector Allocation
- Options (PUTS/CALLS) → **Hedge** sector (purple `#c084fc`), not "Unknown"
- Option detection regex: `\d{2}[A-Za-z]{3}\d{2}[PC]|\d{6}[PC]\d` (requires date pattern — avoids false positives on WDC, KLIC etc.)
- ETF holdings distributed by sector weight from `sector_cache.json` / `sector_overrides.json`
- Manual overrides: `sector_overrides.json`, `subsector_mapping.json`, `currency_overrides.json`

### Balance Tables
- **Individual account tabs:** compact mode — Account/Type columns hidden, total row hidden, `width:auto`
- **All Accounts / Household tabs:** full mode — shows Account/Type columns and colored total row
- P&L% = `pnl / (equity − pnl) * 100` (cost_basis = equity − pnl)
- Total row background: green (`#d4edda`) if P&L ≥ 0, red (`#f8d7da`) if negative

---

## Key Files

| File | Location | Purpose |
|------|----------|---------|
| `questrade_api.py` | `src/` | Questrade OAuth client — handles token refresh and API calls |
| `ChanduAPITracker` | `Config/` | Chandu's Questrade refresh token ⚠️ sensitive |
| `NanduAPITracker` | `Config/` | Nandu's Questrade refresh token ⚠️ sensitive |
| `sector_cache.json` | `Config/` | yfinance sector data cache (auto-updated on new symbols) |
| `sector_overrides.json` | `Config/` | Manual sector corrections per symbol |
| `subsector_mapping.json` | `Config/` | Symbol → subsector label mapping |
| `currency_overrides.json` | `Config/` | Correct Questrade currency misclassifications |

---

## Streamlit Cloud Deployment

The portfolio is accessible via the TradeAgent Streamlit app at `pages/2_Portfolio.py`.
It is gated: only the user logged in as **"Nanda"** can see it.

### Token Setup on Cloud
Streamlit Cloud has no `Config/` directory. Tokens are read from `st.secrets` and written to `/tmp/` at startup:
```toml
# Streamlit Cloud secrets (Settings → Secrets)
[questrade]
chandu_token = "<current refresh token>"
nandu_token  = "<current refresh token>"   # optional
```

### Writable paths on Cloud
Only `/tmp/` is writable. All cache files fall back:
- `sector_cache.json` → `/tmp/sector_cache.json`
- `description_cache.json` → `/tmp/description_cache.json`
- `ChanduAPITracker` token → `/tmp/ChanduAPITracker`

`Config/` files (overrides, subsector mapping) are read-only at deploy time — they must exist in the repo copy at `TradeAgent/PortfolioReport/Config/`.

---

## ⚠️ Questrade Token Rotation — Known Gotcha

**Problem:** Questrade refresh tokens are single-use and rotate on every API call.
- After every successful call, the old token is dead and a new one is saved to `Config/ChanduAPITracker`.
- If you run `generate_report.py` locally, the local `Config/ChanduAPITracker` is updated but Streamlit Cloud secrets still has the old (dead) token → `Authentication failed: Bad Request`.

**Current workaround:**
1. Check current token: `cat PortfolioReport/Config/ChanduAPITracker`
2. Update Streamlit Cloud → App → ⋮ → Settings → Secrets → set `chandu_token` to the new value
3. Save (app reboots automatically)

**Rule: only refresh from one place at a time** — either always use the cloud page, or always run locally and keep secrets in sync. Mixing both without syncing breaks the other.

**How to fix properly (future improvement):**
- After a successful Questrade auth, call the Streamlit REST API to update the secret automatically
- Or: store the live token in a shared persistent store (GCP Secret Manager, Firestore, or a private GitHub repo) and have both local and cloud read/write from there
- Or: run a nightly GitHub Actions job that refreshes the token and updates both the file and the secret

---

## Running the Report

```bash
cd PortfolioReport
python3 generate_report.py
```

Output: `Reports/PortfolioReport_DDMMYYYY.html`

### When the API fails
The HTML report will display a yellow banner with:
- Which person's fetch failed and the error
- Auth errors → prompts to log in to Questrade to refresh the token
- Connection errors → prompts to check internet and retry

---

## Known Issues / Limitations

| # | Status | Issue |
|---|--------|-------|
| 1 | ✅ Fixed | Header/content column mismatch in positions tables |
| 2 | ✅ Fixed | Currency button highlight broken across multiple account tabs |
| 3 | ✅ Fixed | WDC/KLIC wrongly classified as options |
| 4 | ✅ Fixed | SPY put showing as Unknown sector |
| 5 | ✅ Fixed | Symbol = Description same value — Questrade returns `symbolDescription: null`; fixed with `or symbol` fallback + yfinance lookup |
| 6 | ✅ Fixed | Balance total row misaligned (colspan bug) |
| 7 | ✅ Fixed | Streamlit Cloud path errors — `Config/` doesn't exist on cloud; all writable paths fall back to `/tmp/` |
| 8 | ⚠️ Expected | API values lag web UI by minutes (`isRealTime: false`) — ~99.3% accurate |
| 9 | ✅ Fixed | **Token rotation** — GitHub Gist sync keeps local + cloud tokens in sync automatically |
| 10 | ℹ️ Non-critical | Activities endpoint `startTime` validation error — activities not used |
| 11 | ✅ Fixed | Nandu's `NanduAPITracker` populated — Nandu data now fetches live |

---

## Excel Backup

`src/data.py` retains `latest_file()` and `load_person()` for loading Excel activity files from `Data/`.  
These are not called by default — restore calls in `main()` if Questrade API becomes unavailable.

---

## Tier 1 CAN SLIM Improvements (Completed ✅)

**Screener enhancements in `src/screener.py` & `src/fmp.py`:**

### C (Current Earnings) — Institutional-Grade Setup
- **Requires ALL three:**
  1. EPS growth ≥ 25% (current Q vs same Q last year)
  2. Accelerating (each of last 4 quarters > prior quarter)
  3. Revenue growth > 0 (both rising together = institutional confirmation)
- Data from `fetch_earnings_growth()` which fetches 8 quarterly records, computes YoY growth and acceleration trend

### A (Annual Growth + ROE)
- ROE ≥ 17% (O'Neil's institutional sponsor threshold) → letter awarded
- Data from `fetch_key_metrics()`

### N (New) / S (Volume) / M (Market) / L (Leader)
- **N** — Near pivot / breakout (price within 10% of 52-week high)
- **S** — Volume surge (today > 1.5× vol avg), displays float & avg volume from profiles
- **M** — Market direction (price above 200 DMA)
- **L** — Leader RS > 70 using IBD-weighted formula (2× recent 63d, 1× prior 63-day periods)

### I (Institutional) 
- Float heuristic (10M–500M shares typical for institutional buyers). Full implementation in Tier 2.

**Result table displays:**
- All 8 CAN SLIM letters with ✅/❌ status
- EPS Growth %, Rev Growth %, Acceleration (✅/❌)
- ROE %, Earnings date, Float, Avg Volume
- Score ≥5 for buy zone (requires strong multi-factor institutional setup)

---

## Next Steps

### High priority
- [x] **Fix token rotation** — GitHub Gist-based sync (automatic, no cloud deploy needed)
- [x] Add Nandu's Questrade API refresh token to `Config/NanduAPITracker`
- [ ] **Tier 2 CAN SLIM** — Institutional ownership, Follow-through day detection, Industry group rank

### Medium priority
- [ ] **Auto-sync `PortfolioReport/src/`** to `TradeAgent/PortfolioReport/src/` — currently a manual `cp` step; a pre-commit hook or symlink would eliminate drift
- [ ] Fix `startTime` parameter for activities endpoint if activity tracking is needed

### Low priority / cleanup
- [ ] Remove Excel backup code once API is proven stable (optional)

---

## CAN SLIM Data Accuracy — Improvement Roadmap

Every CAN SLIM row needs better data. This section tracks what to build, in order of effort vs impact.

### Current gaps by letter

| Letter | Criterion | Current state | Gap |
|--------|-----------|---------------|-----|
| **C** | Current quarterly EPS & revenue | FMP quarterly income-statement + yfinance fallback | Missing earnings surprise (beat/miss vs estimate). TSX stocks may lag. |
| **A** | Annual EPS growth + ROE | FMP annual income-statement + yfinance fallback | ROE not fetched. Need FMP `/key-metrics` for ROE ≥ 17% check. |
| **N** | New product / mgmt / industry shift | FMP `/news` (3 headlines) | Headlines only — no catalyst classification, no sentiment score. Manual remains best until DeepVue screenshots are integrated. |
| **S** | Volume surge on breakout day | yfinance last-day vol vs 50-day avg | We check today's volume, not the volume on the actual breakout pivot day. Need to detect the pivot and check vol on that specific day. |
| **L** | Leader — RS Rating ≥ 80 | Our computed RS (1-yr return ratio) | IBD formula weights last 63 days at 2×. Industry group rank missing. Our RS is approximate. |
| **I** | Institutional sponsorship (rising) | Manual review only | **Biggest gap.** FMP `/institutional-ownership` is free tier and gives holder count per quarter — automates this entirely. |
| **M** | Market direction | SPY/QQQ vs 50/200-SMA | Too basic. O'Neil's real definition is a **follow-through day (FTD)**: index up ≥1.25% on higher vol than prior day, on day 4+ of a rally attempt. Also missing: advance/decline breadth, new highs vs lows count. |

---

### Recommended build order

#### Tier 1 — Low effort, high value (do these first)

- [x] **Earnings surprise for C** — `FMP /earnings-surprises` → implemented in `fmp.fetch_earnings_surprise()`. Returns beat/miss counts and avg surprise %.
- [x] **ROE for A** — `FMP /key-metrics` → implemented in `fmp.fetch_key_metrics()`. Checks if ROE ≥ 17% (O'Neil threshold).
- [x] **Earnings next date** — `FMP /earnings-calendar` → implemented in `fmp.fetch_earnings_calendar()`. Returns next earnings date.
- [x] **IBD-weighted RS formula for L** — implemented in `screener._ibd_rs_rating()`. Uses 2× weight on last 63 days, 1× for prior 63-day periods.
- [x] **Float & avg volume for S** — extracted from FMP `/profile`. `fetch_profiles()` now returns float and avgVolume fields.

#### Tier 2 — Medium effort, fills biggest gaps

- [ ] **Institutional ownership for I** — `FMP /institutional-ownership?symbol=X` returns quarterly holder count and % ownership. Compare current vs prior quarter → show rising/falling trend. Automates I completely. 2–3 hours.
- [ ] **Follow-through day detection for M** — compute from SPY/QQQ daily data already downloaded via yfinance:
  1. Detect a rally attempt (index closes up after a low)
  2. Count days since attempt
  3. FTD = day 4+ where index closes up ≥1.25% on volume higher than prior session
  4. Distribution day = index drops ≥0.2% on higher volume
  Show: "Confirmed uptrend (FTD: 2025-06-14)" or "Rally attempt day 3 — not yet confirmed"
  3–4 hours.
- [ ] **Industry group rank for L** — `FMP /sector-performance` or build a mini-screener that compares sector/industry RS vs SPY. Show where the stock's sector ranks. 2–3 hours.

#### Tier 3 — Hard / requires manual input or paid data

- [ ] **N — catalyst classification** — DeepVue screenshot upload to populate new product / management change / industry shift. TODO stub already in code.
- [ ] **Base pattern recognition for S** — detect cup-with-handle, flat base, etc. from chart data. Complex, needs chart analysis logic.
- [ ] **IBD RS Rating (paid)** — most accurate L source. Only needed if our computed RS proves unreliable.
- [ ] **News sentiment scoring** — Alpha Vantage or similar for N. Paid tier needed for meaningful signal.

---

### Data sources reference

| Source | Endpoint | Free tier | What it gives |
|--------|----------|-----------|---------------|
| FMP | `/income-statement?period=quarter` | ✅ Yes | Quarterly EPS, revenue (C) |
| FMP | `/income-statement?period=annual` | ✅ Yes | Annual EPS 4 years (A) |
| FMP | `/key-metrics` | ✅ Yes | ROE, P/E, debt ratios (A) |
| FMP | `/earnings-surprises` | ✅ Yes | Beat/miss vs estimate (C) |
| FMP | `/earnings-calendar` | ✅ Yes | Next earnings date |
| FMP | `/institutional-ownership` | ✅ Yes | Holder count QoQ (I) |
| FMP | `/news` | ✅ Yes | Headlines (N) |
| FMP | `/profile` | ✅ Yes | Float, avg vol, sector (S, L) |
| FMP | `/sector-performance` | ✅ Yes | Sector RS vs SPY (L) |
| yfinance | `download()` daily OHLCV | ✅ Yes | Price, volume history (S, L, M) |
| yfinance | `quarterly_income_stmt` | ⚠️ May block on cloud | Quarterly net income fallback (C) |
| IBD | RS Rating | ❌ Paid | Gold standard for L |
| DeepVue | Screenshot upload | 🔲 Manual | C, A, I (future) |
