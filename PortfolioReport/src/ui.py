"""Shared Streamlit UI components for portfolio analysis and dashboard."""

import math
import streamlit as st
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MARKET_RULES   = {"canslim_m", "market_golden_cross", "market_death_cross", "market_distribution_day"}
_BUY_RULES      = {"canslim_l", "canslim_s", "sell_new_high_low_vol"}
_BUY_CATEGORIES = {"CANSLIM", "BUY_ENTRY"}
_SELL_TECH_RULES = {
    "sell_below_200", "sell_sma50_break", "sell_poor_rs", "sell_distribution_volume",
    "sell_peak_decline", "sell_consecutive_down", "sell_closing_low",
    "sell_above_200_extended", "sell_exhaustion_sharan", "sell_failed_breakout",
}
_SELL_POS_RULES = {"position_limit", "sell_hard_stop", "sell_alt_stop", "sell_take_profits", "sell_climax_run"}

STATUS_ICON = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "N/A": "—"}
URGENCY_ORDER = {"IMMEDIATE": 0, "THIS WEEK": 1, "MONITOR": 2, "NONE": 3}

_VERDICT_COLOR = {
    "buy":   ("Buy candidate",    "🟢"),
    "sell":  ("Sell",             "🔴"),
    "watch": ("Watch — conflict", "🟡"),
    "hold":  ("Hold",             "🔵"),
    "mon":   ("Monitor",          "⚪"),
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
    cat = rules_lookup.get(r["rule_id"], {}).get("category", "")
    return cat in _BUY_CATEGORIES


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
    results       = holding["rule_results"]
    urgency       = holding["worst_urgency"]
    buy_pass, buy_total, sell_fail, sell_total = _scores(results, rules_lookup)

    market_r = next((r for r in results if r["rule_id"] == "canslim_m"), None)
    market_ok = (market_r["status"] == "PASS") if market_r else True

    # Collect top reasons
    fired_sell = sorted(
        [r for r in results if r["status"] in ("FAIL", "WARN") and r.get("value")],
        key=lambda r: URGENCY_ORDER.get(r.get("urgency", "NONE"), 3)
    )
    fired_buy  = [r for r in results if r["status"] == "PASS" and _is_buy_rule(r, rules_lookup)]

    def _buy_reason():
        parts = [f"{r['name']}: {r['value']}" for r in fired_buy[:3]]
        return " · ".join(parts) if parts else "no buy signals"

    def _sell_reason():
        parts = [f"{r['name']}: {r['value']}" for r in fired_sell[:3]]
        return " · ".join(parts) if parts else ""

    if urgency == "IMMEDIATE":
        return "sell", _sell_reason()
    if buy_pass >= 3 and market_ok and sell_fail <= 1:
        return "buy", _buy_reason()
    if buy_pass >= 3 and sell_fail >= 2:
        reason = _buy_reason() + " BUT " + _sell_reason()
        return "watch", reason
    if sell_fail >= 3 or urgency == "THIS WEEK":
        return "sell", _sell_reason()
    if buy_pass >= 2:
        parts = [_buy_reason()]
        if _sell_reason():
            parts.append(_sell_reason())
        return "hold", " · ".join(parts)
    return "mon", _sell_reason() or _buy_reason()


# ---------------------------------------------------------------------------
# Detail section — one stock full breakdown
# ---------------------------------------------------------------------------

def _section_table(results: list, rules_lookup: dict):
    """Render a clean detail table for a group of rule results."""
    if not results:
        st.caption("No rules in this section.")
        return
    rows = []
    for r in results:
        desc = rules_lookup.get(r["rule_id"], {}).get("description", "")
        rows.append({
            "Rule":    r["name"],
            "Desc":    desc,
            "Value":   r.get("value", "—"),
            "Detail":  r.get("detail", ""),
            "Status":  STATUS_ICON.get(r["status"], "—"),
            "Action":  r.get("action") or "—",
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Rule":   st.column_config.TextColumn("Rule", width="medium"),
            "Desc":   st.column_config.TextColumn("Description", width="large"),
            "Value":  st.column_config.TextColumn("Value", width="medium"),
            "Detail": st.column_config.TextColumn("Detail", width="large"),
            "Status": st.column_config.TextColumn("Status", width="small"),
            "Action": st.column_config.TextColumn("Action", width="medium"),
        },
    )


def _render_detail(holding: dict, rules_lookup: dict):
    vtype, reason = _verdict(holding, rules_lookup)
    label, icon   = _VERDICT_COLOR[vtype]

    price_str = _fmt_price(holding["current_price"])
    pl_str    = _fmt_pct(holding["pl_pct"]) if holding["pl_pct"] != 0.0 else ""
    pl_part   = f" · P&L {pl_str}" if pl_str else ""

    st.markdown(f"### {holding['symbol']} &nbsp; {price_str}{pl_part} &nbsp; {icon} {label}")
    st.caption(reason)
    st.divider()

    results      = holding["rule_results"]
    market_res   = [r for r in results if r["rule_id"] in _MARKET_RULES]
    buy_res      = [r for r in results if _is_buy_rule(r, rules_lookup)]
    sell_tech_res= [r for r in results if r["rule_id"] in _SELL_TECH_RULES]
    sell_pos_res = [r for r in results if r["rule_id"] in _SELL_POS_RULES]

    if market_res:
        st.markdown("#### 🌍 Market conditions")
        _section_table(market_res, rules_lookup)
        st.markdown("")

    if buy_res:
        st.markdown("#### 🟢 Buy signals")
        _section_table(buy_res, rules_lookup)
        st.markdown("")

    if sell_tech_res:
        st.markdown("#### 🔴 Sell signals — technical")
        _section_table(sell_tech_res, rules_lookup)
        st.markdown("")

    if sell_pos_res:
        st.markdown("#### 🟠 Sell signals — position")
        if holding["pl_pct"] == 0.0 and holding["account"] == "Watchlist":
            st.caption("Position rules not applicable — watchlist stock (no cost data).")
        _section_table(sell_pos_res, rules_lookup)


# ---------------------------------------------------------------------------
# Main decision view
# ---------------------------------------------------------------------------

def render_decision_view(holdings: list, rules: list, show_account: bool = True, key: str = "decision"):
    """Two focused tables (buy | sell) + click-to-expand detail section below."""
    if not holdings:
        st.info("No holdings found.")
        return

    rules_lookup = {r["rule_id"]: r for r in rules}

    # Augment each holding with verdict + scores
    enriched = []
    for h in holdings:
        vtype, reason = _verdict(h, rules_lookup)
        bp, bt, sf, st_ = _scores(h["rule_results"], rules_lookup)
        label, icon = _VERDICT_COLOR[vtype]
        enriched.append({
            **h,
            "_vtype":      vtype,
            "_reason":     reason,
            "_label":      label,
            "_icon":       icon,
            "_buy_pass":   bp,
            "_buy_total":  bt,
            "_sell_fail":  sf,
            "_sell_total": st_,
        })

    # Split into buy candidates and sell alerts
    buy_candidates = sorted(
        [h for h in enriched if h["_vtype"] in ("buy", "watch", "hold")],
        key=lambda h: (-h["_buy_pass"], h["symbol"])
    )
    sell_alerts = sorted(
        [h for h in enriched if h["_vtype"] in ("sell", "watch")],
        key=lambda h: (URGENCY_ORDER.get(h["worst_urgency"], 3), h["symbol"])
    )
    # stocks that are only "mon" — appear in neither table → add to buy side
    monitor_only = [h for h in enriched if h["_vtype"] == "mon"]
    buy_candidates += sorted(monitor_only, key=lambda h: h["symbol"])

    def _make_buy_df(items):
        rows = []
        for h in items:
            row = {
                "Stock":      f"{h['symbol']} {_fmt_price(h['current_price'])}",
                "Verdict":    f"{h['_icon']} {h['_label']}",
                "Market":     next((STATUS_ICON.get(r["status"],"—") + " " + r["value"]
                                    for r in h["rule_results"] if r["rule_id"] == "canslim_m"), "—"),
                "Buy score":  f"{h['_buy_pass']}/{h['_buy_total']}",
                "Key reason": h["_reason"][:60],
            }
            if show_account:
                row["Account"] = h["account"]
            rows.append(row)
        return pd.DataFrame(rows)

    def _make_sell_df(items):
        rows = []
        for h in items:
            row = {
                "Stock":      f"{h['symbol']} {_fmt_price(h['current_price'])}",
                "Urgency":    h["worst_urgency"],
                "Sell score": f"{h['_sell_fail']}/{h['_sell_total']}",
                "Key reason": h["_reason"][:60],
                "P&L":        _fmt_pct(h["pl_pct"]) if h["pl_pct"] != 0.0 else "—",
            }
            if show_account:
                row["Account"] = h["account"]
            rows.append(row)
        return pd.DataFrame(rows)

    # ---- Two tables ----
    col_buy, col_sell = st.columns(2)

    selected_sym = st.session_state.get(f"{key}_selected")

    with col_buy:
        st.markdown("#### 🟢 Buy candidates")
        buy_df = _make_buy_df(buy_candidates)
        sel_buy = st.dataframe(
            buy_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=f"{key}_buy_tbl",
        )
        rows_sel = sel_buy.selection.get("rows", []) if sel_buy else []
        if rows_sel:
            sym = buy_candidates[rows_sel[0]]["symbol"]
            st.session_state[f"{key}_selected"] = sym
            st.session_state[f"{key}_selected_src"] = "buy"
            selected_sym = sym

    with col_sell:
        st.markdown("#### 🔴 Sell alerts")
        if sell_alerts:
            sell_df = _make_sell_df(sell_alerts)
            sel_sell = st.dataframe(
                sell_df,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key=f"{key}_sell_tbl",
            )
            rows_sel = sel_sell.selection.get("rows", []) if sel_sell else []
            if rows_sel:
                sym = sell_alerts[rows_sel[0]]["symbol"]
                st.session_state[f"{key}_selected"] = sym
                st.session_state[f"{key}_selected_src"] = "sell"
                selected_sym = sym
        else:
            st.success("No sell alerts — all positions look healthy.")

    # ---- Detail section ----
    st.divider()
    if selected_sym:
        match = next((h for h in enriched if h["symbol"] == selected_sym), None)
        if match:
            _render_detail(match, rules_lookup)
    else:
        st.caption("Click any row above to see the full rule breakdown for that stock.")


# ---------------------------------------------------------------------------
# Rule settings panel (shared between portfolio analysis and dashboard)
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
