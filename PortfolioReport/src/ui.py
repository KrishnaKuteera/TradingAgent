"""Shared Streamlit UI components used by both portfolio analysis and dashboard."""

import streamlit as st
import pandas as pd

STATUS_ICON   = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "N/A": "—"}
URGENCY_BADGE = {
    "IMMEDIATE": "🔴 IMMEDIATE",
    "THIS WEEK": "🟡 THIS WEEK",
    "MONITOR":   "🔵 MONITOR",
    "NONE":      "✅ OK",
}
URGENCY_ORDER = {"IMMEDIATE": 0, "THIS WEEK": 1, "MONITOR": 2, "NONE": 3}


def render_holdings_matrix(holdings: list, rules: list, show_account: bool = True):
    """Render the full holdings matrix with one column per enabled auto-rule.

    show_account=False hides the Account column (useful for single-context views).
    """
    if not holdings:
        st.info("No holdings found.")
        return

    auto_rules = [r for r in rules if r.get("enabled") and r.get("automatable")]
    sorted_h   = sorted(holdings, key=lambda x: (URGENCY_ORDER.get(x["worst_urgency"], 3), x["symbol"]))

    rows = []
    for h in sorted_h:
        rule_map = {r["rule_id"]: r for r in h["rule_results"]}
        row = {"Alert": URGENCY_BADGE.get(h["worst_urgency"], "✅ OK"),
               "Symbol": h["symbol"]}
        if show_account:
            row["Account"] = h["account"]
        row["P&L %"] = f"{h['pl_pct']:+.1f}%" if h["pl_pct"] != 0.0 else "—"
        row["Price"]  = f"${h['current_price']:.2f}" if h["current_price"] else "N/A"
        row["Trend"]  = h["trend"]
        for rule in auto_rules:
            res = rule_map.get(rule["rule_id"])
            row[rule["name"]] = f"{STATUS_ICON.get(res['status'], '—')} {res['value']}" if res else "—"
        rows.append(row)

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("#### Signal Details")
    has_alerts = False
    for h in sorted_h:
        alerts = [r for r in h["rule_results"]
                  if r["status"] in ("FAIL", "WARN") and r.get("detail")]
        if alerts:
            has_alerts = True
            label = f"**{h['symbol']}**"
            if show_account:
                label += f" — {h['account']}"
            st.markdown(label)
            for a in alerts:
                icon = "🔴" if a["status"] == "FAIL" else "🟡"
                tag  = f" `{a['urgency']}`" if a["urgency"] != "NONE" else ""
                st.caption(f"{icon}{tag} **{a['name']}:** {a['detail']}")
    if not has_alerts:
        st.caption("No active signals.")


def render_action_items(actions: list, show_account: bool = True):
    """Render action items grouped by urgency."""
    if not actions:
        st.success("✅ No immediate actions required.")
        return

    immediate = [a for a in actions if a["urgency"] == "IMMEDIATE"]
    this_week = [a for a in actions if a["urgency"] == "THIS WEEK"]
    monitor   = [a for a in actions if a["urgency"] == "MONITOR"]

    _hide = {"priority", "detail", "urgency", "_rules"}
    if not show_account:
        _hide.add("account")

    def _show(items):
        df = pd.DataFrame(items)
        visible = [c for c in df.columns if c not in _hide]
        st.dataframe(df[visible], use_container_width=True, hide_index=True)

    if immediate:
        st.error(f"🔴 {len(immediate)} IMMEDIATE action(s)")
        _show(immediate)
    if this_week:
        st.warning(f"🟡 {len(this_week)} action(s) this week")
        _show(this_week)
    if monitor:
        with st.expander(f"🔵 {len(monitor)} item(s) to monitor"):
            _show(monitor)


def render_rule_settings(rules: list, save_rule_fn=None) -> list:
    """Render the rule management UI.

    save_rule_fn: callable(rule_id, enabled, params) — if None, toggles are read-only.
    Returns updated rules list.
    """
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

    updated = []
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
