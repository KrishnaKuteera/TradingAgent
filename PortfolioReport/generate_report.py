#!/usr/bin/env python3
"""Thin entry point — assembles modules from src/ and writes the HTML report."""

from datetime import datetime
from pathlib import Path

from src.data import load_all_from_questrade, get_fx
from src.calc import get_all_symbols, load_sector_data, load_subsector_data, load_currency_overrides
from src.report import build_html
from src.config import REPORTS_DIR

FOLDER = Path(__file__).parent


def main():
    print("Fetching data from Questrade API...")
    chandu_data, nandu_data, errors = load_all_from_questrade()
    fx = get_fx(chandu_data)
    print("✓ Data loaded from Questrade API")

    for data in [chandu_data, nandu_data]:
        if "Positions" in data and not data["Positions"].empty:
            pos_df = data["Positions"]
            mask = ~pos_df["Equity Description"].str.upper().str.contains("DOLLAR|CASH", na=False)
            data["Positions"] = pos_df[mask].reset_index(drop=True)

    print("Loading sector data...")
    symbols            = get_all_symbols(chandu_data, nandu_data)
    sector_data        = load_sector_data(symbols)
    subsector_data     = load_subsector_data()
    currency_overrides = load_currency_overrides()
    print("✓ Using market values from Questrade API")

    report_date = datetime.today().strftime("%d %b %Y")
    out_name    = f"PortfolioReport_{datetime.today().strftime('%d%m%Y')}.html"
    out_path    = REPORTS_DIR / out_name

    html = build_html(chandu_data, nandu_data, report_date, fx,
                      sector_data, subsector_data, currency_overrides, errors)
    out_path.write_text(html, encoding="utf-8")
    print(f"Report written: {out_path}")


if __name__ == "__main__":
    main()
