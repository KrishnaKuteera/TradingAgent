import sys
import os
import json
import importlib.util
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="Portfolio Analysis", page_icon="📊", layout="wide")

PORTFOLIO_USER = "Nanda"

# --- Auth guard ---
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page first.")
    st.stop()

if st.session_state.get("username", "").lower() != PORTFOLIO_USER.lower():
    st.error("Access denied.")
    st.stop()

# --- Portfolio module path ---
_here            = os.path.dirname(os.path.abspath(__file__))
_portfolio_local = os.path.join(_here, '..', '..', 'PortfolioReport')
_portfolio_cloud = os.path.join(_here, '..', 'PortfolioReport')
_portfolio_path  = _portfolio_local if os.path.isdir(_portfolio_local) else _portfolio_cloud
if _portfolio_path not in sys.path:
    sys.path.insert(0, _portfolio_path)

try:
    from src.data    import load_all_from_questrade, get_fx
    from src.signals import run_signals
    from src.ui      import render_decision_view, render_rule_settings
except ImportError as e:
    st.error(f"Portfolio module not available: {e}")
    st.stop()

# --- Load rules_sheet via explicit path ---
try:
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
# Constants
# ---------------------------------------------------------------------------

URGENCY_ORDER = {"IMMEDIATE": 0, "THIS WEEK": 1, "MONITOR": 2, "NONE": 3}
URGENCY_BADGE = {
    "IMMEDIATE": "🔴 IMMEDIATE",
    "THIS WEEK": "🟡 THIS WEEK",
    "MONITOR":   "🔵 MONITOR",
    "NONE":      "✅ OK",
}


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


# ---------------------------------------------------------------------------
# Rule Settings panel
# ---------------------------------------------------------------------------

def _render_rule_settings(rules: list) -> list:
    save_fn = save_rule if _rules_available else None
    return render_rule_settings(rules, save_rule_fn=save_fn)


# ---------------------------------------------------------------------------
# Claude briefing
# ---------------------------------------------------------------------------

def _claude_briefing(actions: list, holdings: list) -> str:
    try:
        import anthropic
        key = None
        try:
            key = st.secrets.get("anthropic", {}).get("api_key")
        except Exception:
            pass
        key = key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return "⚠️ No Anthropic API key in secrets ([anthropic] api_key)."

        client  = anthropic.Anthropic(api_key=key)
        payload = {
            "run_date": datetime.today().strftime("%Y-%m-%d"),
            "actions":  actions[:30],
            "holdings": [{"symbol": h["symbol"], "account": h["account"],
                          "pl_pct": h["pl_pct"], "trend": h["trend"],
                          "worst_urgency": h["worst_urgency"]} for h in holdings],
        }

        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": f"""You are a portfolio advisor using O'Neil / CAN SLIM methodology.

{json.dumps(payload, indent=2)}

Give a concise weekly briefing:
1. IMMEDIATE ACTIONS (anything urgent)
2. POSITIONS TO WATCH (warnings)
3. OVERALL HEALTH (1-2 sentences)

Be direct, use actual symbols and amounts. Under 300 words."""}]
        )
        return msg.content[0].text
    except Exception as e:
        return f"Claude API error: {e}"


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

st.title("📊 Portfolio Analysis & Actions")

_setup_tokens()

# Load rules
rules = []
if _rules_available:
    try:
        rules = fetch_rules()
    except Exception as e:
        st.warning(f"Could not load rules: {e}")

# Two main tabs
tab_analysis, tab_rules = st.tabs(["📊 Analysis & Actions", "⚙️ Rule Settings"])

with tab_rules:
    st.header("⚙️ Rule Settings")
    st.markdown("All rules from your Google Sheets **Rules** tab. Toggle or adjust thresholds here — changes save instantly.")
    if _rules_available and rules:
        rules = _render_rule_settings(rules)
    else:
        st.warning("Rules not available. Check that the **Rules** tab exists in StockTracker.")

with tab_analysis:
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        run_btn = st.button("▶️ Run Analysis", type="primary", use_container_width=True)
    with col2:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.pop("signals_result", None)
            st.session_state.pop("signals_ts", None)
            st.rerun()
    with col3:
        if "signals_ts" in st.session_state:
            st.caption(f"Last run: {st.session_state['signals_ts']}")

    if run_btn or "signals_result" in st.session_state:
        if run_btn:
            _setup_tokens()
            with st.spinner("Loading portfolio data..."):
                try:
                    chandu_data, nandu_data, errors = load_all_from_questrade()
                    stale = [m for p, m in errors if p == "__stale__"]
                    if stale:
                        st.warning(f"⚠️ Showing cached snapshot from {stale[0]}.")
                    fx = get_fx(chandu_data)
                    # Filter cash positions
                    for data in [chandu_data, nandu_data]:
                        pos = data.get("Positions")
                        if pos is not None and not pos.empty:
                            mask = ~pos["Equity Description"].str.upper().str.contains("DOLLAR|CASH", na=False)
                            data["Positions"] = pos[mask].reset_index(drop=True)
                except Exception as e:
                    st.error(f"Failed to load portfolio: {e}")
                    st.stop()

            with st.spinner("Fetching live technical data for all holdings… (30–60 sec)"):
                try:
                    result = run_signals(chandu_data, nandu_data, rules)
                    st.session_state["signals_result"] = result
                    st.session_state["signals_ts"]     = datetime.now().strftime("%d %b %Y %H:%M")
                except Exception as e:
                    st.error(f"Signals engine error: {e}")
                    st.stop()

        result   = st.session_state.get("signals_result", {})
        holdings = result.get("holdings", [])
        actions  = result.get("actions",  [])

        render_decision_view(holdings, rules, show_account=True, key="portfolio")

        st.divider()

        # Claude briefing
        st.header("🤖 AI Weekly Briefing")
        if st.button("Ask Claude", type="secondary"):
            with st.spinner("Asking Claude..."):
                st.markdown(_claude_briefing(actions, holdings))

    else:
        st.info("Click **▶️ Run Analysis** to evaluate all O'Neil rules against your current holdings.")
