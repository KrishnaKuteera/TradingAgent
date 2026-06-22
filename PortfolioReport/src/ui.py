"""Shared Streamlit UI components for portfolio analysis and dashboard."""

import math
import streamlit as st
import pandas as pd


def _trading_rules_url() -> str:
    """Return URL to the TradingRules Google Sheet tab (set [google] sheet_url in Streamlit secrets)."""
    try:
        url = st.secrets.get("google", {}).get("sheet_url", "")
        if url:
            return url
    except Exception:
        pass
    return "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit#gid=0"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MARKET_RULES    = {"canslim_m", "market_golden_cross", "market_death_cross", "market_distribution_day"}
_BUY_RULES       = {"canslim_l", "canslim_s"}
# sell_new_high_low_vol is a caution/sell signal, not a buy signal — kept in sell_tech
_BUY_CATEGORIES  = {"CANSLIM", "BUY_ENTRY"}
_SELL_TECH_RULES = {
    "sell_below_200", "sell_sma50_break", "sell_poor_rs", "sell_distribution_volume",
    "sell_peak_decline", "sell_consecutive_down", "sell_closing_low",
    "sell_above_200_extended", "sell_exhaustion_sharan", "sell_failed_breakout",
    "sell_new_high_low_vol",  # near new high on weak volume = unconfirmed breakout
}
_SELL_POS_RULES  = {"position_limit", "sell_hard_stop", "sell_alt_stop", "sell_take_profits", "sell_climax_run"}

STATUS_ICON   = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "N/A": "—"}
URGENCY_ORDER = {"IMMEDIATE": 0, "THIS WEEK": 1, "MONITOR": 2, "NONE": 3}

_VERDICT_META = {
    "buy":   ("🟢 Buy candidate",      0),
    "hold":  ("🔵 Hold — keep position", 1),
    "watch": ("🟡 Watch — mixed signals", 2),
    "sell":  ("🔴 Sell",               3),
    "mon":   ("⚪ Monitor",            4),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_price(val) -> str:
    try:
        f = float(val)
        return f"${f:.2f}" if math.isfinite(f) and f > 0 else "N/A"
    except Exception:
        return "N/A"


def _fmt_pct(val) -> str:
    try:
        f = float(val)
        return f"{f:+.1f}%" if math.isfinite(f) and f != 0.0 else "—"
    except Exception:
        return "—"


def _is_buy_rule(r: dict, rules_lookup: dict) -> bool:
    if r["rule_id"] in _BUY_RULES:
        return True
    return rules_lookup.get(r["rule_id"], {}).get("category", "") in _BUY_CATEGORIES


def _classify(r: dict, rules_lookup: dict) -> str:
    rid = r["rule_id"]
    if rid in _MARKET_RULES:
        return "market"
    if _is_buy_rule(r, rules_lookup):
        return "buy"
    if rid in _SELL_POS_RULES:
        return "pos"
    return "sell_tech"


def _scores(rule_results: list, rules_lookup: dict):
    buy_pass = buy_total = sell_fail = sell_total = 0
    for r in rule_results:
        cls = _classify(r, rules_lookup)
        if cls == "buy":
            buy_total += 1
            if r["status"] == "PASS":
                buy_pass += 1
        elif cls in ("sell_tech", "pos"):
            sell_total += 1
            if r["status"] in ("FAIL", "WARN"):
                sell_fail += 1
    return buy_pass, buy_total, sell_fail, sell_total


def _verdict(holding: dict, rules_lookup: dict):
    results  = holding["rule_results"]
    urgency  = holding["worst_urgency"]
    buy_pass, buy_total, sell_fail, sell_total = _scores(results, rules_lookup)

    market_r  = next((r for r in results if r["rule_id"] == "canslim_m"), None)
    market_ok = (market_r["status"] == "PASS") if market_r else True

    fired_sell = sorted(
        [r for r in results if r["status"] in ("FAIL", "WARN") and r.get("value")],
        key=lambda r: URGENCY_ORDER.get(r.get("urgency", "NONE"), 3),
    )
    fired_buy = [r for r in results if r["status"] == "PASS" and _is_buy_rule(r, rules_lookup)]

    def _buy_reason():
        return " · ".join(f"{r['name']}: {r['value']}" for r in fired_buy[:3]) or "no buy signals"

    def _sell_reason():
        return " · ".join(f"{r['name']}: {r['value']}" for r in fired_sell[:3])

    # Thresholds calibrated to current automatable buy rules:
    # C (EPS) and A (annual EPS) reliably produce PASS/FAIL.
    # S fires only near breakout; L requires paid IBD — both mostly N/A.
    # So buy_pass=2 means both C+A pass = strong fundamental setup.
    if urgency == "IMMEDIATE":
        return "sell", _sell_reason()
    if buy_pass >= 2 and market_ok and sell_fail == 0:
        return "buy", _buy_reason()
    if buy_pass >= 2 and market_ok and sell_fail <= 2:
        return "buy", _buy_reason()
    if buy_pass >= 2 and sell_fail >= 3:
        return "watch", _buy_reason() + " BUT " + _sell_reason()
    if sell_fail >= 4 or urgency == "THIS WEEK":
        return "sell", _sell_reason()
    if buy_pass >= 1:
        parts = [_buy_reason()]
        if _sell_reason():
            parts.append(_sell_reason())
        return "hold", " · ".join(parts)
    return "mon", _sell_reason() or _buy_reason()


# ---------------------------------------------------------------------------
# Price performance (on demand for one stock)
# ---------------------------------------------------------------------------

def _render_price_performance(symbol: str):
    import yfinance as yf
    import pytz
    from datetime import datetime

    st.markdown("#### 📈 Price performance")
    with st.spinner(f"Loading price history for {symbol}…"):
        try:
            hist = yf.download(symbol, period="1y", progress=False, auto_adjust=True)
            if hist.empty:
                st.warning("No price data available.")
                return
            close = hist["Close"].squeeze().dropna()
            if close.empty:
                st.warning("No price data available.")
                return
            cur      = float(close.iloc[-1])
            end_date = datetime.now(pytz.timezone("America/Toronto")).date()

            periods = {"1D": 2, "5D": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}
            records = []
            for label, n in periods.items():
                if len(close) >= n:
                    past = float(close.iloc[-n])
                    pct  = (cur - past) / past * 100
                    records.append({"Period": label, "Then": past, "Now": cur, "_pct": pct,
                                    "Change": f"{pct:+.2f}%", "Value": f"${past:.2f} → ${cur:.2f}"})
            ys = close[close.index.year == end_date.year]
            if len(ys) > 0:
                past = float(ys.iloc[0])
                pct  = (cur - past) / past * 100
                records.append({"Period": "YTD", "Then": past, "Now": cur, "_pct": pct,
                                "Change": f"{pct:+.2f}%", "Value": f"${past:.2f} → ${cur:.2f}"})

            df = pd.DataFrame(records)[["Period", "Value", "Change"]]

            def _color_change(val: str):
                try:
                    num = float(val.replace("%", "").replace("+", ""))
                    if num > 0:
                        intensity = min(int(abs(num) * 8), 120)
                        return f"background-color: rgba(0,180,0,{intensity/255:.2f}); color: #003300; font-weight:600"
                    elif num < 0:
                        intensity = min(int(abs(num) * 8), 120)
                        return f"background-color: rgba(220,0,0,{intensity/255:.2f}); color: #fff; font-weight:600"
                except Exception:
                    pass
                return ""

            styled = df.style.applymap(_color_change, subset=["Change"])
            st.dataframe(styled, use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"Could not load price history: {e}")


# ---------------------------------------------------------------------------
# CANSLIM section
# ---------------------------------------------------------------------------

def _render_canslim_section(holding: dict, rules_lookup: dict):
    """Render full C/A/N/S/L/I/M breakdown with live earnings data and news."""
    st.markdown("#### 📊 CAN SLIM analysis")

    symbol  = holding["symbol"]
    results = holding["rule_results"]

    canslim_l = next((r for r in results if r["rule_id"] == "canslim_l"), None)
    canslim_s = next((r for r in results if r["rule_id"] == "canslim_s"), None)
    canslim_m = next((r for r in results if r["rule_id"] == "canslim_m"), None)

    # Fetch earnings growth (C and A) — graceful fallback
    eg = {}
    try:
        from .fmp import fetch_earnings_growth
        eg = fetch_earnings_growth(symbol)
    except Exception:
        pass

    # News for N — prefer cache (n_headlines + n_catalyst from weekly refresh), fall back to FMP
    n_catalyst = eg.get("n_catalyst") if eg else None
    n_headlines = eg.get("n_headlines", []) if eg else []
    news_items = []
    if n_headlines:
        # Cache has headlines from yfinance (populated by refresh_cache.py)
        news_items = [{"title": h, "date": ""} for h in n_headlines[:3]]
    else:
        try:
            from .fmp import fetch_news
            news_items = fetch_news(symbol, limit=3)
        except Exception:
            pass
    news_str = " | ".join(f"{n['title'][:90]}" for n in news_items) if news_items else ""

    # Format C values
    def _pct_str(val, suffix=""):
        if val is None: return "—"
        sign = "+" if val >= 0 else ""
        return f"{sign}{val:.1f}%{suffix}"

    c_eps_g      = eg.get("c_eps_growth")
    c_rev_g      = eg.get("c_rev_growth")
    c_qtr        = eg.get("c_quarter", "")
    c_eps_v      = eg.get("c_eps_current")
    c_prior      = eg.get("c_eps_prior")
    c_growths    = eg.get("c_qtr_growths", [])   # [current, Q-1, Q-2, Q-3]
    c_qtr_eps    = eg.get("c_qtr_eps", [])
    c_accel      = eg.get("c_accelerating", False)
    c_accel_full = eg.get("c_accel_full", False)

    c_value = "—"
    if c_eps_g is not None:
        # Quarter label — try c_quarter, then first label from acceleration list
        _labels = eg.get("c_qtr_labels", [])
        _raw_label = c_qtr or (_labels[0] if _labels else None)
        qtr_label = f"Q {_raw_label}" if _raw_label else "Latest Q"

        c_value = f"{qtr_label} EPS {_pct_str(c_eps_g)} vs year-ago Q"
        if c_eps_v is not None and c_prior is not None:
            c_value += f"  (${c_eps_v:.2f} vs ${c_prior:.2f})"
        if c_rev_g is not None:
            c_value += f"  |  Rev {_pct_str(c_rev_g)} vs year-ago Q"
        elif c_rev_g is None:
            c_value += "  |  Rev N/A"

        # 4Q acceleration trend — show what we have (even if only 2 quarters)
        if len(c_growths) >= 2:
            parts = []
            for i, g in enumerate(reversed(c_growths)):
                eps_i = len(c_growths) - 1 - i
                if eps_i < len(c_qtr_eps):
                    parts.append(f"${c_qtr_eps[eps_i]}({g:+.1f}%)")
                else:
                    parts.append(f"{g:+.1f}%")
            trend = " → ".join(parts)
            accel_icon = "✅ Accelerating" if c_accel_full else ("↗ Improving" if c_accel else "⚠️ Decelerating")
            n = len(c_growths)
            c_value += f"\n{n}Q trend: {trend}  {accel_icon}"
        else:
            c_value += "\nAcceleration: insufficient data (need 8+ quarters of history)"

    c_status = "—"
    if c_eps_g is not None:
        has_accel_data = len(c_growths) >= 2
        if c_eps_g >= 25 and (c_accel or not has_accel_data):
            c_status = "✅"  # strong growth; acceleration confirmed or data unavailable
        elif c_eps_g >= 25:
            c_status = "⚠️"  # growth ≥25% but decelerating — worth watching
        elif c_eps_g >= 0:
            c_status = "⚠️"  # positive but below threshold
        else:
            c_status = "❌"  # negative EPS growth

    # Format A values
    a_g3   = eg.get("a_eps_growth_3yr")
    a_yrs  = eg.get("a_eps_years", [])
    a_value = "—"
    if a_g3 is not None:
        a_value = f"3-yr avg EPS growth: {_pct_str(a_g3)}"
        if a_yrs:
            detail_parts = [f"{y['year']}: ${y['eps']:.2f}" for y in a_yrs if y.get("eps")]
            a_value += "  |  " + " → ".join(detail_parts)

    a_status = "—"
    if a_g3 is not None:
        a_status = "✅" if a_g3 >= 25 else ("⚠️" if a_g3 >= 0 else "❌")

    rows = [
        # C — Current quarterly earnings
        {
            "Letter": "C",
            "Criterion": "Current quarterly EPS & revenue growth",
            "Status": c_status,
            "Action": "Buy" if c_status == "✅" else ("Watch" if c_status == "⚠️" else "Avoid") if c_status != "—" else "—",
            "Value": c_value,
            "Rule Description": (
                "O'Neil: EPS growth ≥ 25% vs same quarter last year, accelerating quarter over quarter. "
                "Revenue growth should confirm — both rising together = institutional-grade setup. "
                # TODO: DeepVue screenshot upload — to override with audited EPS data
            ),
        },
        # A — Annual earnings growth
        {
            "Letter": "A",
            "Criterion": "Annual EPS growth — 3-year track record",
            "Status": a_status,
            "Action": "Buy" if a_status == "✅" else ("Watch" if a_status == "⚠️" else "Avoid") if a_status != "—" else "—",
            "Value": a_value,
            "Rule Description": (
                "O'Neil: 3-yr avg annual EPS growth ≥ 25%. ROE ≥ 17%. "
                "Consistent compounding — avoid one-time jumps. "
                # TODO: DeepVue screenshot upload — to override with audited data
            ),
        },
        # N — New product / service / management / industry conditions
        {
            "Letter": "N",
            "Criterion": "New product, service, management, or industry shift",
            "Status": "📋 Manual review",
            "Action": "—",
            "Value": (
                f"Claude: {n_catalyst['summary']}" if n_catalyst and n_catalyst.get("score") != "none"
                else (news_items[0]["title"][:80] if news_items else "No recent news found")
            ),
            "Rule Description": (
                "O'Neil: the biggest stock moves are driven by something NEW — "
                "a breakthrough product, new CEO, disruptive technology, or a major industry change. "
                + (f"Claude assessment: {n_catalyst['catalyst_type']} ({n_catalyst['score']}). " if n_catalyst and n_catalyst.get("score") != "none" else "")
                + ("Latest headlines: " + news_str if news_str else "No recent headlines found.")
            ),
        },
        # S — Supply and demand (volume)
        {
            "Letter": "S",
            "Criterion": "Supply & demand — volume surge on breakout",
            "Status": STATUS_ICON.get(canslim_s["status"], "—") if canslim_s else "—",
            "Action": (canslim_s.get("action") or "—") if canslim_s else "—",
            "Value": canslim_s["value"] if canslim_s else "—",
            "Rule Description": canslim_s["detail"] if canslim_s and canslim_s.get("detail") else (
                "Volume should be ≥ 40–50% above average on a breakout day. "
                "Heavy volume = institutional buying. Thin volume breakouts fail."
            ),
        },
        # L — Leader (RS rating — manual review; our computed RS is approximate)
        {
            "Letter": "L",
            "Criterion": "Leader or Laggard — RS rating vs market",
            "Status": "📋 Manual review",
            "Action": "—",
            "Value": canslim_l["value"] if canslim_l else "—",
            "Rule Description": (
                "O'Neil: buy the top 1–2 stocks in a leading industry group. "
                "Avoid sympathy plays. IBD RS Rating ≥ 80 required. "
                "Our computed RS is an estimate — verify on IBD / TradingView. "
                + (canslim_l["detail"] if canslim_l and canslim_l.get("detail") else "")
            ),
        },
        # I — Institutional sponsorship (manual)
        {
            "Letter": "I",
            "Criterion": "Institutional sponsorship & ownership trend",
            "Status": "📋 Manual review",
            "Action": "—",
            "Value": "—",
            "Rule Description": (
                # TODO: DeepVue screenshot upload
                "O'Neil: rising number of institutional owners (funds, pensions) QoQ. "
                "Quality matters — top-rated funds buying is a strong signal. "
                "Upload DeepVue screenshot to auto-fill."
            ),
        },
        # M — Market direction
        {
            "Letter": "M",
            "Criterion": "Market direction — SPY + QQQ in confirmed uptrend",
            "Status": STATUS_ICON.get(canslim_m["status"], "—") if canslim_m else "—",
            "Action": (canslim_m.get("action") or "—") if canslim_m else "—",
            "Value": canslim_m["value"] if canslim_m else "—",
            "Rule Description": (
                "O'Neil: never fight the market. 3 out of 4 stocks follow the market direction. "
                "Buy only in confirmed uptrends (follow-through day). "
                + (canslim_m["detail"] if canslim_m and canslim_m.get("detail") else "SPY + QQQ vs 50/200-SMA.")
            ),
        },
    ]

    _html_table(rows, [
        ("Letter",           "",                 "small"),
        ("Criterion",        "Criterion",        ""),
        ("Status",           "Status",           "small"),
        ("Action",           "Action",           "small"),
        ("Value",            "Value",            ""),
        ("Rule Description", "Rule Description", "desc"),
    ])


# ---------------------------------------------------------------------------
# Rule table (buy/sell sections)
# ---------------------------------------------------------------------------

def _rule_table(results: list, rules_lookup: dict):
    if not results:
        st.caption("No rules in this section.")
        return
    rows = []
    for r in results:
        desc = rules_lookup.get(r["rule_id"], {}).get("description", "")
        rows.append({
            "Rule":             r["name"],
            "Status":           STATUS_ICON.get(r["status"], "—"),
            "Action":           r.get("action") or "—",
            "Value":            r.get("value", "—"),
            "Rule Description": r.get("detail", "") or desc,
        })
    _html_table(rows, [
        ("Rule",             "Rule",             ""),
        ("Status",           "Status",           "small"),
        ("Action",           "Action",           "small"),
        ("Value",            "Value",            ""),
        ("Rule Description", "Rule Description", "desc"),
    ])


# ---------------------------------------------------------------------------
# Detail panel — full breakdown for one stock
# ---------------------------------------------------------------------------

def _render_detail(holding: dict, rules_lookup: dict):
    vtype, reason = _verdict(holding, rules_lookup)
    label, _      = _VERDICT_META[vtype]
    price_str     = _fmt_price(holding["current_price"])
    pl_str        = _fmt_pct(holding["pl_pct"]) if holding["pl_pct"] != 0.0 else ""
    pl_part       = f" &nbsp;·&nbsp; P&L {pl_str}" if pl_str else ""

    st.markdown(f"### {holding['symbol']} &nbsp; {price_str}{pl_part} &nbsp;&nbsp; {label}")
    st.caption(reason)
    st.divider()

    results       = holding["rule_results"]
    buy_res       = [r for r in results if _is_buy_rule(r, rules_lookup)]
    sell_tech_res = [r for r in results if r["rule_id"] in _SELL_TECH_RULES]
    sell_pos_res  = [r for r in results if r["rule_id"] in _SELL_POS_RULES]
    is_watchlist  = holding.get("account") == "Watchlist"

    # 1 — CANSLIM
    _render_canslim_section(holding, rules_lookup)
    st.markdown("")

    # 2 — Buy signals
    if buy_res:
        st.markdown("#### 🟢 Buy signals")
        _rule_table(buy_res, rules_lookup)
        st.markdown("")

    # 3 — Sell: technical
    if sell_tech_res:
        st.markdown("#### 🔴 Sell signals — technical")
        _rule_table(sell_tech_res, rules_lookup)
        st.markdown("")

    # 4 — Sell: position
    st.markdown("#### 🟠 Sell signals — position")
    if is_watchlist:
        st.caption("Not applicable — watchlist stock. Position rules require cost basis data.")
    else:
        _rule_table(sell_pos_res, rules_lookup)
    st.markdown("")

    # 5 — Price performance (on demand)
    _render_price_performance(holding["symbol"])


# ---------------------------------------------------------------------------
# Main decision view
# ---------------------------------------------------------------------------

_TABLE_CSS = """
<style>
.wt-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
    font-family: sans-serif;
    margin-bottom: 1rem;
}
.wt-table th {
    background: #f0f2f6;
    text-align: left;
    padding: 6px 10px;
    border-bottom: 2px solid #d0d3da;
    font-weight: 600;
    white-space: nowrap;
}
.wt-table td {
    padding: 6px 10px;
    border-bottom: 1px solid #e8eaf0;
    vertical-align: top;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.45;
}
.wt-table tr:hover td { background: #f7f8fc; }
.wt-table td.num { text-align: right; }
.wt-table td.small { white-space: nowrap; width: 1%; }
.wt-table td.desc { min-width: 260px; }
</style>
"""


def _html_table(rows: list, col_specs: list):
    """Render a list of dicts as a wrapping HTML table.

    col_specs: list of (key, header, css_class)
    """
    import html
    headers = "".join(f"<th>{h}</th>" for _, h, _ in col_specs)
    body = ""
    for row in rows:
        cells = ""
        for key, _, cls in col_specs:
            val = str(row.get(key, "") or "")
            cells += f'<td class="{cls}">{html.escape(val)}</td>'
        body += f"<tr>{cells}</tr>"
    st.markdown(
        f'{_TABLE_CSS}<table class="wt-table"><thead><tr>{headers}</tr></thead><tbody>{body}</tbody></table>',
        unsafe_allow_html=True,
    )


def render_decision_view(holdings: list, rules: list, show_account: bool = True, key: str = "decision"):
    """Single table (all stocks) + click-to-expand detail section below."""
    if not holdings:
        st.info("No holdings found.")
        return

    rules_lookup = {r["rule_id"]: r for r in rules}

    # Data source links
    sheet_url = _trading_rules_url()
    st.markdown(
        f"**Data:** [Yahoo Finance](https://finance.yahoo.com) · "
        f"[FMP](https://financialmodelingprep.com) · "
        f"[TradingRules (Google Sheet)]({sheet_url}) · "
        f"[CAN SLIM — IBD](https://www.investors.com/ibd-university/can-slim/)  "
        f"&nbsp;|&nbsp; Click a row → full CAN SLIM breakdown below.",
        unsafe_allow_html=False,
    )

    # Market banner — same for every stock, show once at top
    any_h = holdings[0] if holdings else None
    if any_h:
        market_r = next((r for r in any_h["rule_results"] if r["rule_id"] == "canslim_m"), None)
        if market_r:
            icon = STATUS_ICON.get(market_r["status"], "—")
            val  = market_r["value"]
            detail = market_r.get("detail", "")
            st.info(f"**Market (M):** {icon} {val}{'  —  ' + detail if detail else ''}", icon="🌍")

    # Augment each holding with verdict + scores
    enriched = []
    for h in holdings:
        vtype, reason        = _verdict(h, rules_lookup)
        # Portfolio mode: already own the stock — "buy" means "keep holding", not "enter new position"
        if show_account and vtype == "buy":
            vtype = "hold"
        bp, bt, sf, st_      = _scores(h["rule_results"], rules_lookup)
        label, sort_order    = _VERDICT_META[vtype]
        enriched.append({
            **h,
            "_vtype":       vtype,
            "_reason":      reason,
            "_label":       label,
            "_sort":        sort_order,
            "_buy_pass":    bp,
            "_buy_total":   bt,
            "_sell_fail":   sf,
            "_sell_total":  st_,
        })

    # Sort: urgency first, then verdict order, then buy score desc
    enriched.sort(key=lambda h: (
        URGENCY_ORDER.get(h["worst_urgency"], 3),
        h["_sort"],
        -h["_buy_pass"],
        h["symbol"],
    ))

    # Build display DataFrame — Reason is NOT in the dataframe (can't wrap in st.dataframe)
    # It is shown as a styled callout below the table for the selected row.
    rows = []
    for h in enriched:
        tv_url = f"https://www.tradingview.com/chart/?symbol={h['symbol'].replace('.TO', ':TSX').replace('.', ':')}"
        row = {
            "Stock":   f"{h['symbol']}  {_fmt_price(h['current_price'])}",
            "TV":      tv_url,
            "Verdict": h["_label"],
            "Buy ✓":   f"{h['_buy_pass']}/{h['_buy_total']}",
            "Sell ✗":  f"{h['_sell_fail']}/{h['_sell_total']}",
        }
        if show_account:
            row["Account"] = h["account"]
            row["P&L"]     = _fmt_pct(h["pl_pct"]) if h["pl_pct"] != 0.0 else "—"
        rows.append(row)

    df = pd.DataFrame(rows)

    base_cols = ["Stock", "TV", "Verdict", "Buy ✓", "Sell ✗"]
    if show_account:
        base_cols += ["Account", "P&L"]
    df = df[base_cols]

    col_cfg = {
        "Stock":   st.column_config.TextColumn("Stock",    width="medium"),
        "TV":      st.column_config.LinkColumn("📈 Chart", width="small", display_text="TradingView"),
        "Verdict": st.column_config.TextColumn("Verdict",  width="small"),
        "Buy ✓":   st.column_config.TextColumn("Buy ✓",    width="small"),
        "Sell ✗":  st.column_config.TextColumn("Sell ✗",   width="small"),
    }
    if show_account:
        col_cfg["Account"] = st.column_config.TextColumn("Account", width="small")
        col_cfg["P&L"]     = st.column_config.TextColumn("P&L",     width="small")

    sel = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"{key}_tbl",
        column_config=col_cfg,
    )

    # Track selection
    rows_sel = sel.selection.get("rows", []) if sel else []
    if rows_sel and rows_sel[0] < len(enriched):
        st.session_state[f"{key}_selected"] = enriched[rows_sel[0]]["symbol"]

    selected_sym = st.session_state.get(f"{key}_selected")
    selected_h   = next((h for h in enriched if h["symbol"] == selected_sym), None) if selected_sym else None

    # Reason callout — shown for selected row, readable full text outside dataframe
    st.markdown("")
    if selected_h:
        vtype = selected_h["_vtype"]
        color = {"buy": "#d4edda", "watch": "#fff3cd", "sell": "#f8d7da",
                 "hold": "#cce5ff", "mon": "#e2e3e5"}.get(vtype, "#f0f2f6")
        border = {"buy": "#28a745", "watch": "#ffc107", "sell": "#dc3545",
                  "hold": "#0066cc", "mon": "#6c757d"}.get(vtype, "#999")
        import html as _html
        reason_safe = _html.escape(selected_h["_reason"])
        st.markdown(
            f'<div style="background:{color};border-left:4px solid {border};'
            f'padding:10px 14px;border-radius:4px;font-size:0.88rem;line-height:1.6;">'
            f'<strong>{selected_h["symbol"]}</strong> — {reason_safe}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("⬆ Click any row to see its reason and full CAN SLIM breakdown below.")

    # Full detail section
    st.divider()
    if selected_h:
        tv_url = f"https://www.tradingview.com/chart/?symbol={selected_h['symbol'].replace('.TO', ':TSX').replace('.', ':')}"
        _render_detail(selected_h, rules_lookup)
        st.markdown(f"[Open {selected_h['symbol']} on TradingView ↗]({tv_url})")


# ---------------------------------------------------------------------------
# Rule settings panel
# ---------------------------------------------------------------------------

def render_rule_settings(rules: list, save_rule_fn=None) -> list:
    if not rules:
        st.info("No rules loaded.")
        return rules

    categories = {}
    for r in rules:
        categories.setdefault(r["category"], []).append(r)

    cat_labels = {
        "CANSLIM":        "📈 CAN SLIM Criteria",
        "BUY_ENTRY":      "🟢 Buy Entry Rules",
        "POSITION":       "⚖️ Position Sizing",
        "SELL_DEFENSIVE": "🛡️ Sell — Defensive (Cut Losses)",
        "SELL_OFFENSIVE": "💰 Sell — Offensive (Lock Gains)",
        "MARKET":         "🌍 Market Conditions",
        "PERSONAL":       "🧠 Personal Rules (Sharan's)",
    }

    updated  = []
    readonly = save_rule_fn is None
    if readonly:
        st.caption("ℹ️ View-only — rule changes can be made by the portfolio owner.")

    for cat, cat_rules in categories.items():
        label = cat_labels.get(cat, cat)
        with st.expander(label, expanded=False):
            if not readonly:
                st.caption("Toggle rules on/off or adjust thresholds. Changes save to Google Sheets.")
            for rule in cat_rules:
                auto_tag = "" if rule["automatable"] else " *(manual review)*"
                if readonly:
                    icon = "✅" if rule["enabled"] else "☐"
                    st.markdown(f"{icon} **{rule['name']}**{auto_tag}")
                    if rule.get("description"):
                        st.caption(rule["description"])
                    updated.append(rule)
                    st.divider()
                    continue

                enabled = st.checkbox(
                    f"**{rule['name']}**{auto_tag}",
                    value=rule["enabled"],
                    key=f"rule_{rule['rule_id']}_enabled",
                    help=rule.get("description", ""),
                )
                new_params = dict(rule["params"])
                if rule["params"] and rule["automatable"]:
                    cols = st.columns(min(len(rule["params"]), 4))
                    for i, (k, v) in enumerate(rule["params"].items()):
                        if isinstance(v, (int, float)):
                            new_val = cols[i % len(cols)].number_input(
                                k, value=float(v), step=0.5,
                                key=f"rule_{rule['rule_id']}_{k}",
                            )
                            new_params[k] = new_val

                if enabled != rule["enabled"] or new_params != rule["params"]:
                    save_rule_fn(rule["rule_id"], enabled, new_params)

                updated.append({**rule, "enabled": enabled, "params": new_params})
                st.divider()

    return updated
