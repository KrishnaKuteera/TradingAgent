"""Shared Streamlit UI components for portfolio analysis and dashboard."""

import math
import streamlit as st
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MARKET_RULES    = {"canslim_m", "market_golden_cross", "market_death_cross", "market_distribution_day"}
_BUY_RULES       = {"canslim_l", "canslim_s", "sell_new_high_low_vol"}
_BUY_CATEGORIES  = {"CANSLIM", "BUY_ENTRY"}
_SELL_TECH_RULES = {
    "sell_below_200", "sell_sma50_break", "sell_poor_rs", "sell_distribution_volume",
    "sell_peak_decline", "sell_consecutive_down", "sell_closing_low",
    "sell_above_200_extended", "sell_exhaustion_sharan", "sell_failed_breakout",
}
_SELL_POS_RULES  = {"position_limit", "sell_hard_stop", "sell_alt_stop", "sell_take_profits", "sell_climax_run"}

STATUS_ICON   = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "N/A": "—"}
URGENCY_ORDER = {"IMMEDIATE": 0, "THIS WEEK": 1, "MONITOR": 2, "NONE": 3}

_VERDICT_META = {
    "buy":   ("🟢 Buy candidate",    0),
    "watch": ("🟡 Watch — conflict", 1),
    "sell":  ("🔴 Sell",             2),
    "hold":  ("🔵 Hold",             3),
    "mon":   ("⚪ Monitor",          4),
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

    if urgency == "IMMEDIATE":
        return "sell", _sell_reason()
    if buy_pass >= 3 and market_ok and sell_fail <= 1:
        return "buy", _buy_reason()
    if buy_pass >= 3 and sell_fail >= 2:
        return "watch", _buy_reason() + " BUT " + _sell_reason()
    if sell_fail >= 3 or urgency == "THIS WEEK":
        return "sell", _sell_reason()
    if buy_pass >= 2:
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
            hist = yf.Ticker(symbol).history(period="1y")
            if hist.empty:
                st.warning("No price data available.")
                return
            cur = hist["Close"].iloc[-1]
            end_date = datetime.now(pytz.timezone("America/Toronto")).date()
            periods = {"1D": 2, "5D": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}
            row = {"Period": [], "Price then": [], "Price now": [], "Change": []}
            for label, n in periods.items():
                if len(hist) >= n:
                    past = hist["Close"].iloc[-n]
                    pct  = (cur - past) / past * 100
                    row["Period"].append(label)
                    row["Price then"].append(f"${past:.2f}")
                    row["Price now"].append(f"${cur:.2f}")
                    row["Change"].append(f"{pct:+.2f}%")
            ys = hist[hist.index.year == end_date.year]
            if len(ys) > 0:
                past = ys["Close"].iloc[0]
                pct  = (cur - past) / past * 100
                row["Period"].append("YTD")
                row["Price then"].append(f"${past:.2f}")
                row["Price now"].append(f"${cur:.2f}")
                row["Change"].append(f"{pct:+.2f}%")
            st.dataframe(pd.DataFrame(row), use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"Could not load price history: {e}")


# ---------------------------------------------------------------------------
# CANSLIM section
# ---------------------------------------------------------------------------

def _render_canslim_section(holding: dict, rules_lookup: dict):
    """Render full C/A/N/S/L/I/M breakdown with news and manual-review placeholders."""
    st.markdown("#### 📊 CAN SLIM analysis")

    symbol      = holding["symbol"]
    results     = holding["rule_results"]
    tech        = {}  # will be filled from rule values where possible

    # Pull what we already computed from signals
    canslim_l = next((r for r in results if r["rule_id"] == "canslim_l"), None)
    canslim_s = next((r for r in results if r["rule_id"] == "canslim_s"), None)
    canslim_m = next((r for r in results if r["rule_id"] == "canslim_m"), None)
    near_high  = next((r for r in results if r["rule_id"] == "sell_new_high_low_vol"), None)
    peak       = next((r for r in results if r["rule_id"] == "sell_peak_decline"), None)

    # Try to fetch news (free tier — graceful fallback)
    news_items = []
    try:
        from .fmp import fetch_news
        news_items = fetch_news(symbol, limit=3)
    except Exception:
        pass

    news_str = ""
    if news_items:
        news_str = " | ".join(f"{n['date']}: {n['title'][:80]}" for n in news_items)

    rows = [
        # C — Current quarterly earnings (manual)
        {
            "Letter": "C",
            "Criterion": "Current quarterly earnings",
            "Status": "📋 Manual review",
            "Action": "—",
            "Value": "—",
            "Detail": (
                # TODO: DeepVue screenshot upload — parse EPS & revenue growth from screenshot
                "Upload DeepVue screenshot to auto-fill. "
                "Look for: EPS growth ≥ 25% QoQ, accelerating revenue."
            ),
        },
        # A — Annual earnings growth (manual)
        {
            "Letter": "A",
            "Criterion": "Annual earnings growth (3-year)",
            "Status": "📋 Manual review",
            "Action": "—",
            "Value": "—",
            "Detail": (
                # TODO: DeepVue screenshot upload
                "Upload DeepVue screenshot to auto-fill. "
                "Look for: 3-yr avg EPS growth ≥ 25%, ROE ≥ 17%."
            ),
        },
        # N — New product / catalyst / near high
        {
            "Letter": "N",
            "Criterion": "New catalyst / near 52-week high",
            "Status": STATUS_ICON.get(canslim_s["status"] if canslim_s else "N/A", "—"),
            "Action": (canslim_s.get("action") or "—") if canslim_s else "—",
            "Value": (peak["value"] if peak else "—") + (" | " + near_high["value"] if near_high else ""),
            "Detail": (
                (peak["detail"] + " " if peak and peak.get("detail") else "") +
                (f"Recent news: {news_str}" if news_str else "No recent news found.")
            ),
        },
        # S — Supply and demand (volume)
        {
            "Letter": "S",
            "Criterion": "Supply & demand — volume on breakout",
            "Status": STATUS_ICON.get(canslim_s["status"], "—") if canslim_s else "—",
            "Action": (canslim_s.get("action") or "—") if canslim_s else "—",
            "Value": canslim_s["value"] if canslim_s else "—",
            "Detail": canslim_s["detail"] if canslim_s and canslim_s.get("detail") else "Volume data from yfinance.",
        },
        # L — Leader (RS rating)
        {
            "Letter": "L",
            "Criterion": "Leader — RS rating ≥ 80",
            "Status": STATUS_ICON.get(canslim_l["status"], "—") if canslim_l else "—",
            "Action": (canslim_l.get("action") or "—") if canslim_l else "—",
            "Value": canslim_l["value"] if canslim_l else "—",
            "Detail": (
                (canslim_l["detail"] if canslim_l and canslim_l.get("detail") else "") +
                " Stock should be in top 20% of market for relative strength."
            ),
        },
        # I — Institutional sponsorship (manual)
        {
            "Letter": "I",
            "Criterion": "Institutional sponsorship",
            "Status": "📋 Manual review",
            "Action": "—",
            "Value": "—",
            "Detail": (
                # TODO: DeepVue screenshot upload
                "Upload DeepVue screenshot to auto-fill. "
                "Look for: increasing institutional ownership QoQ, quality funds buying."
            ),
        },
        # M — Market direction
        {
            "Letter": "M",
            "Criterion": "Market direction — SPY + QQQ uptrend",
            "Status": STATUS_ICON.get(canslim_m["status"], "—") if canslim_m else "—",
            "Action": (canslim_m.get("action") or "—") if canslim_m else "—",
            "Value": canslim_m["value"] if canslim_m else "—",
            "Detail": canslim_m["detail"] if canslim_m and canslim_m.get("detail") else "SPY + QQQ vs 50/200-SMA.",
        },
    ]

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Letter":    st.column_config.TextColumn("",          width=30),
            "Criterion": st.column_config.TextColumn("Criterion", width="medium"),
            "Status":    st.column_config.TextColumn("Status",    width="small"),
            "Action":    st.column_config.TextColumn("Action",    width="small"),
            "Value":     st.column_config.TextColumn("Value",     width="medium"),
            "Detail":    st.column_config.TextColumn("Detail / News", width="large"),
        },
    )


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
            "Rule":   r["name"],
            "Status": STATUS_ICON.get(r["status"], "—"),
            "Action": r.get("action") or "—",
            "Value":  r.get("value", "—"),
            "Detail": r.get("detail", "") or desc,
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Rule":   st.column_config.TextColumn("Rule",   width="medium"),
            "Status": st.column_config.TextColumn("Status", width="small"),
            "Action": st.column_config.TextColumn("Action", width="small"),
            "Value":  st.column_config.TextColumn("Value",  width="medium"),
            "Detail": st.column_config.TextColumn("Detail", width="large"),
        },
    )


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

def render_decision_view(holdings: list, rules: list, show_account: bool = True, key: str = "decision"):
    """Single table (all stocks) + click-to-expand detail section below."""
    if not holdings:
        st.info("No holdings found.")
        return

    rules_lookup = {r["rule_id"]: r for r in rules}

    # Data source links
    st.markdown(
        "**Data sources:** "
        "[Yahoo Finance](https://finance.yahoo.com) · "
        "[Financial Modeling Prep](https://financialmodelingprep.com) · "
        "[O'Neil / IBD Methodology](https://www.investors.com/ibd-university/can-slim/)  &nbsp;|&nbsp; "
        "Click any row to open full CAN SLIM detail. "
        "Stock name links to [TradingView](https://www.tradingview.com).",
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

    # Build display DataFrame — column order: Stock | Verdict | Buy | Sell | [Account | P&L] | Reason
    rows = []
    for h in enriched:
        sym   = h["symbol"].split(".")[0]  # strip .TO etc for cleaner display
        tv_url = f"https://www.tradingview.com/chart/?symbol={h['symbol'].replace('.TO', ':TSX').replace('.', ':')}"
        row = {
            "Stock":   f"{h['symbol']}  {_fmt_price(h['current_price'])}",
            "TV":      tv_url,
            "Verdict": h["_label"],
            "Buy ✓":   f"{h['_buy_pass']}/{h['_buy_total']}",
            "Sell ✗":  f"{h['_sell_fail']}/{h['_sell_total']}",
            "Reason":  h["_reason"],  # full text, let it wrap
        }
        if show_account:
            row["Account"] = h["account"]
            row["P&L"]     = _fmt_pct(h["pl_pct"]) if h["pl_pct"] != 0.0 else "—"
        rows.append(row)

    df = pd.DataFrame(rows)

    # Column order
    base_cols = ["Stock", "TV", "Verdict", "Buy ✓", "Sell ✗"]
    if show_account:
        base_cols += ["Account", "P&L"]
    base_cols.append("Reason")
    df = df[base_cols]

    col_cfg = {
        "Stock":   st.column_config.TextColumn("Stock",    width="medium"),
        "TV":      st.column_config.LinkColumn("📈 Chart", width="small", display_text="TradingView"),
        "Verdict": st.column_config.TextColumn("Verdict",  width="small"),
        "Buy ✓":   st.column_config.TextColumn("Buy ✓",    width="small"),
        "Sell ✗":  st.column_config.TextColumn("Sell ✗",   width="small"),
        "Reason":  st.column_config.TextColumn("Reason",   width="large"),
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

    # Detail section
    st.divider()
    rows_sel = sel.selection.get("rows", []) if sel else []
    if rows_sel:
        idx = rows_sel[0]
        st.session_state[f"{key}_selected"] = enriched[idx]["symbol"]

    selected_sym = st.session_state.get(f"{key}_selected")
    if selected_sym:
        match = next((h for h in enriched if h["symbol"] == selected_sym), None)
        if match:
            tv_url = f"https://www.tradingview.com/chart/?symbol={match['symbol'].replace('.TO', ':TSX').replace('.', ':')}"
            _render_detail(match, rules_lookup)
            st.markdown(f"[Open {match['symbol']} on TradingView ↗]({tv_url})")
    else:
        st.caption("Click any row to see the full CAN SLIM breakdown and signals for that stock.")


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
