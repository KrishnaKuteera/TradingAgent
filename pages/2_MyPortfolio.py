import sys
import os
import json
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="Portfolio Report", page_icon="💼", layout="wide")

PORTFOLIO_USER = "Nanda"

# --- Auth guard ---
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page first.")
    st.stop()

if st.session_state.get("username", "").lower() != PORTFOLIO_USER.lower():
    st.error("Access denied.")
    st.stop()

# --- Portfolio module path (must be first in sys.path so 'src' resolves here) ---
_here            = os.path.dirname(os.path.abspath(__file__))
_portfolio_local = os.path.join(_here, '..', '..', 'PortfolioReport')
_portfolio_cloud = os.path.join(_here, '..', 'PortfolioReport')
_portfolio_path  = _portfolio_local if os.path.isdir(_portfolio_local) else _portfolio_cloud
sys.path.insert(0, _portfolio_path)

try:
    from src.data    import load_all_from_questrade, get_fx
    from src.calc    import get_all_symbols, load_sector_data, load_subsector_data, load_currency_overrides
    from src.report  import build_html
    from src.signals import run_signals
except ImportError as e:
    st.error(f"Portfolio module not available: {e}")
    st.stop()

# --- Load rules_sheet via explicit path to avoid src/ package collision ---
try:
    import importlib.util
    _rules_path = os.path.join(_here, '..', 'src', 'rules_sheet.py')
    _spec       = importlib.util.spec_from_file_location("rules_sheet", _rules_path)
    _rules_mod  = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_rules_mod)
    fetch_rules = _rules_mod.fetch_rules
    save_rule   = _rules_mod.save_rule
    _rules_available = True
except Exception:
    _rules_available = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_tokens():
    try:
        if "questrade" in st.secrets:
            from pathlib import Path
            if "chandu_token" in st.secrets["questrade"]:
                Path("/tmp/ChanduAPITracker").write_text(st.secrets["questrade"]["chandu_token"])
            if "nandu_token" in st.secrets["questrade"]:
                Path("/tmp/NanduAPITracker").write_text(st.secrets["questrade"]["nandu_token"])
    except Exception:
        pass


STATUS_ICON = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "N/A": "—"}
URGENCY_COLOR = {
    "IMMEDIATE": "#f8d7da",
    "THIS WEEK": "#fff3cd",
    "MONITOR":   "#d1ecf1",
    "NONE":      "#f8f9fa",
}
URGENCY_BADGE = {
    "IMMEDIATE": "🔴 IMMEDIATE",
    "THIS WEEK": "🟡 THIS WEEK",
    "MONITOR":   "🔵 MONITOR",
    "NONE":      "",
}


def _claude_briefing(actions: list, holdings: list) -> str:
    """Call Claude API and return plain-English briefing."""
    try:
        import anthropic
        key = None
        try:
            key = st.secrets.get("anthropic", {}).get("api_key")
        except Exception:
            pass
        key = key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return "⚠️ No Anthropic API key found in secrets ([anthropic] api_key)."

        client = anthropic.Anthropic(api_key=key)

        payload = {
            "run_date":   datetime.today().strftime("%Y-%m-%d"),
            "actions":    actions[:30],
            "holdings_summary": [
                {"symbol": h["symbol"], "account": h["account"],
                 "pl_pct": h["pl_pct"], "trend": h["trend"],
                 "worst_urgency": h["worst_urgency"]}
                for h in holdings
            ],
        }

        prompt = f"""You are a portfolio advisor using the CAN SLIM / O'Neil methodology.

Below is a JSON summary of my current holdings with all automated rule evaluations completed.

{json.dumps(payload, indent=2)}

Give me a concise plain-English weekly briefing:
1. IMMEDIATE ACTIONS (anything urgent this week)
2. POSITIONS TO WATCH (warnings to monitor)
3. OVERALL PORTFOLIO HEALTH (1-2 sentences)

Be direct, specific, and use the actual stock symbols and dollar amounts from the data.
Keep the total response under 300 words."""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text

    except Exception as e:
        return f"Claude API error: {e}"


# ---------------------------------------------------------------------------
# Rule management sidebar
# ---------------------------------------------------------------------------

def _render_rule_sidebar(rules: list):
    if not rules:
        st.sidebar.info("No rules loaded.")
        return rules

    st.sidebar.header("⚙️ Rule Settings")
    st.sidebar.caption("Toggle or adjust thresholds. Changes save to Google Sheets.")

    categories = {}
    for r in rules:
        categories.setdefault(r["category"], []).append(r)

    updated_rules = []
    for cat, cat_rules in categories.items():
        with st.sidebar.expander(cat, expanded=False):
            for rule in cat_rules:
                col1, col2 = st.columns([3, 1])
                enabled = col1.checkbox(rule["name"], value=rule["enabled"],
                                        key=f"rule_{rule['rule_id']}_enabled",
                                        help=rule["description"])
                if not rule["automatable"]:
                    col2.caption("manual")

                # Editable params
                new_params = dict(rule["params"])
                if enabled and rule["params"] and rule["automatable"]:
                    for k, v in rule["params"].items():
                        if isinstance(v, (int, float)):
                            new_val = st.number_input(
                                f"  {k}", value=float(v), step=0.5,
                                key=f"rule_{rule['rule_id']}_{k}",
                                label_visibility="visible"
                            )
                            new_params[k] = new_val

                # Save if changed
                if enabled != rule["enabled"] or new_params != rule["params"]:
                    save_rule(rule["rule_id"], enabled, new_params)

                updated_rules.append({**rule, "enabled": enabled, "params": new_params})

    return updated_rules


# ---------------------------------------------------------------------------
# Holdings table renderer
# ---------------------------------------------------------------------------

def _render_holdings_table(holdings: list, rules: list):
    if not holdings:
        st.info("No holdings to display.")
        return

    import pandas as pd

    auto_rules = [r for r in rules if r.get("enabled") and r.get("automatable")]

    # Sort holdings: IMMEDIATE first, then THIS WEEK, MONITOR, NONE
    urgency_order = {"IMMEDIATE": 0, "THIS WEEK": 1, "MONITOR": 2, "NONE": 3}
    sorted_holdings = sorted(holdings, key=lambda x: (urgency_order.get(x["worst_urgency"], 3), x["symbol"]))

    # Build one row per stock, one column per rule
    matrix_rows = []
    for h in sorted_holdings:
        rule_map = {r["rule_id"]: r for r in h["rule_results"]}
        row = {
            "Alert":    URGENCY_BADGE.get(h["worst_urgency"], "") or "✅ OK",
            "Symbol":   h["symbol"],
            "Account":  h["account"],
            "P&L %":   f"{h['pl_pct']:+.1f}%",
            "Price":    f"${h['current_price']:.2f}",
            "Trend":    h["trend"],
        }
        for rule in auto_rules:
            res  = rule_map.get(rule["rule_id"])
            if res:
                icon = STATUS_ICON.get(res["status"], "—")
                row[rule["name"]] = f"{icon} {res['value']}"
            else:
                row[rule["name"]] = "—"
        matrix_rows.append(row)

    if matrix_rows:
        matrix_df = pd.DataFrame(matrix_rows)
        st.dataframe(matrix_df, use_container_width=True, hide_index=True)

    # Detail callouts for any FAIL/WARN
    st.markdown("**Signals Detail**")
    has_alerts = False
    for h in sorted_holdings:
        alerts = [r for r in h["rule_results"]
                  if r["status"] in ("FAIL", "WARN") and r.get("detail")]
        if alerts:
            has_alerts = True
            st.markdown(f"**{h['symbol']}** — {h['account']}")
            for a in alerts:
                icon = "🔴" if a["status"] == "FAIL" else "🟡"
                urgency_tag = f" `{a['urgency']}`" if a["urgency"] != "NONE" else ""
                st.caption(f"{icon}{urgency_tag} **{a['name']}:** {a['detail']}")
    if not has_alerts:
        st.caption("No active signals.")


# ---------------------------------------------------------------------------
# Action items table
# ---------------------------------------------------------------------------

def _render_action_items(actions: list):
    if not actions:
        st.success("✅ No immediate actions required across all holdings.")
        return

    import pandas as pd

    immediate = [a for a in actions if a["urgency"] == "IMMEDIATE"]
    this_week = [a for a in actions if a["urgency"] == "THIS WEEK"]
    monitor   = [a for a in actions if a["urgency"] == "MONITOR"]

    if immediate:
        st.error(f"🔴 **{len(immediate)} IMMEDIATE actions required**")
        st.dataframe(pd.DataFrame(immediate)[["symbol","account","action","rule","value","detail"]],
                     use_container_width=True, hide_index=True)

    if this_week:
        st.warning(f"🟡 **{len(this_week)} actions this week**")
        st.dataframe(pd.DataFrame(this_week)[["symbol","account","action","rule","value","detail"]],
                     use_container_width=True, hide_index=True)

    if monitor:
        with st.expander(f"🔵 {len(monitor)} items to monitor", expanded=False):
            st.dataframe(pd.DataFrame(monitor)[["symbol","account","action","rule","value","detail"]],
                         use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

st.title("💼 Portfolio Report")

col1, col2, col3 = st.columns([1, 1, 4])
with col1:
    refresh = st.button("🔄 Refresh Data", use_container_width=True)
with col2:
    run_analysis = st.button("📊 Run Trade Signals", use_container_width=True)

if refresh:
    st.cache_data.clear()
    if "signals_result" in st.session_state:
        del st.session_state["signals_result"]

_setup_tokens()

# Load rules
rules = []
if _rules_available:
    try:
        rules = fetch_rules()
        rules = _render_rule_sidebar(rules)
    except Exception as e:
        st.sidebar.warning(f"Could not load rules: {e}")
else:
    st.sidebar.warning("Rules module not available.")

# Load portfolio data
with st.spinner("Fetching live data from Questrade..."):
    try:
        chandu_data, nandu_data, errors = load_all_from_questrade()

        stale = [msg for person, msg in errors if person == "__stale__"]
        if stale:
            st.warning(f"⚠️ Live data unavailable — showing cached snapshot from {stale[0]}. "
                       "Update the Questrade token in Streamlit secrets and refresh.")
        errors = [(p, m) for p, m in errors if p != "__stale__"]

        fx = get_fx(chandu_data)

        for data in [chandu_data, nandu_data]:
            if "Positions" in data and not data["Positions"].empty:
                pos_df = data["Positions"]
                mask   = ~pos_df["Equity Description"].str.upper().str.contains("DOLLAR|CASH", na=False)
                data["Positions"] = pos_df[mask].reset_index(drop=True)

        symbols            = get_all_symbols(chandu_data, nandu_data)
        sector_data        = load_sector_data(symbols)
        subsector_data     = load_subsector_data()
        currency_overrides = load_currency_overrides()
        report_date        = datetime.today().strftime("%d %b %Y")
        html               = build_html(chandu_data, nandu_data, report_date, fx,
                                        sector_data, subsector_data, currency_overrides, errors)
        st.components.v1.html(html, height=900, scrolling=True)

    except Exception as e:
        st.error(f"Failed to load portfolio: {e}")
        st.stop()

# ---------------------------------------------------------------------------
# Trade Signals Section
# ---------------------------------------------------------------------------

st.divider()
st.header("📊 Trade Signals")

if run_analysis or "signals_result" in st.session_state:
    if run_analysis:
        with st.spinner("Fetching live technical data and evaluating rules… (30–60 sec)"):
            try:
                result = run_signals(chandu_data, nandu_data, rules)
                st.session_state["signals_result"] = result
            except Exception as e:
                st.error(f"Signals engine error: {e}")
                st.stop()

    result   = st.session_state.get("signals_result", {})
    holdings = result.get("holdings", [])
    actions  = result.get("actions",  [])

    # Action Items (top of signals — most important first)
    st.subheader("🎯 Action Items")
    _render_action_items(actions)

    st.divider()

    # Holdings detail table
    st.subheader("📋 Holdings — Rule Breakdown")
    if rules:
        _render_holdings_table(holdings, rules)
    else:
        st.info("Rules not loaded — cannot show rule breakdown.")

    st.divider()

    # Claude briefing
    st.subheader("🤖 AI Briefing")
    if st.button("Get Claude's Weekly Briefing", type="primary"):
        with st.spinner("Asking Claude..."):
            briefing = _claude_briefing(actions, holdings)
        st.markdown(briefing)

else:
    st.info("Click **Run Trade Signals** to evaluate all rules against your current holdings. "
            "This fetches live technical data and takes ~30–60 seconds.")
