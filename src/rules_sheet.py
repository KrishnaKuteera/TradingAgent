"""Read and write trading rules from the Google Sheets 'Rules' tab."""

import json
import os
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

SHEET_NAME = "StockTracker"
RULES_TAB  = "Rules"
SCOPES     = ["https://www.googleapis.com/auth/spreadsheets",
               "https://www.googleapis.com/auth/drive"]


def _get_client():
    json_file = "tradeportfolioagent-8348ccf38790.json"
    if os.path.exists(json_file):
        creds = Credentials.from_service_account_file(json_file, scopes=SCOPES)
    elif "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), scopes=SCOPES)
    else:
        raise RuntimeError("No GCP credentials found")
    return gspread.authorize(creds)


@st.cache_data(ttl=60)
def fetch_rules() -> list:
    """Return all rules from the Rules tab as a list of dicts."""
    client = _get_client()
    sheet  = client.open(SHEET_NAME).worksheet(RULES_TAB)
    rows   = sheet.get_all_records()
    rules  = []
    for row in rows:
        try:
            params = json.loads(row.get("params", "{}") or "{}")
        except Exception:
            params = {}
        rules.append({
            "rule_id":     row.get("rule_id", ""),
            "category":    row.get("category", ""),
            "name":        row.get("name", ""),
            "description": row.get("description", ""),
            "enabled":     str(row.get("enabled", "TRUE")).upper() == "TRUE",
            "automatable": str(row.get("automatable", "FALSE")).upper() == "TRUE",
            "params":      params,
        })
    return [r for r in rules if r["rule_id"]]


def save_rule(rule_id: str, enabled: bool, params: dict) -> None:
    """Persist a rule change (enabled flag + params) back to the sheet."""
    try:
        fetch_rules.clear()
        client = _get_client()
        sheet  = client.open(SHEET_NAME).worksheet(RULES_TAB)
        rows   = sheet.get_all_values()
        if not rows:
            return
        header = [h.lower().strip() for h in rows[0]]
        rid_col    = header.index("rule_id")    + 1
        en_col     = header.index("enabled")    + 1
        params_col = header.index("params")     + 1
        for i, row in enumerate(rows[1:], start=2):
            if len(row) > rid_col - 1 and row[rid_col - 1] == rule_id:
                sheet.update_cell(i, en_col,     "TRUE" if enabled else "FALSE")
                sheet.update_cell(i, params_col, json.dumps(params))
                return
    except Exception as e:
        st.warning(f"Could not save rule {rule_id}: {e}")


def rules_by_id(rules: list) -> dict:
    """Convert list → {rule_id: rule_dict} for fast lookup."""
    return {r["rule_id"]: r for r in rules}
