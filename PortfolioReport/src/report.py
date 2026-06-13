"""HTML report generation: all component builders, CSS, JS, and build_html()."""

import pandas as pd

from .config import SECTOR_COLORS
from .utils import (
    safe_float, conv_cad, conv_usd, get_currency,
    fmt_cad, fmt_usd, fmt_pct, fmt_qty, pnl_class, account_label,
    money_td_native, money_td_multiview,
    money_th, money_th_native,
)
from .calc import (
    consolidate_positions, compute_sector_alloc, compute_subsector_alloc,
    get_subsector,
)
from .data import get_fx


# ---------------------------------------------------------------------------
# Positions tables
# ---------------------------------------------------------------------------

def consolidated_positions_table(df: pd.DataFrame, fx: float, sector_data: dict,
                                  subsector_data: dict, balances: pd.DataFrame = None,
                                  total_mv_with_cash: float = None,
                                  currency_overrides: dict = None):
    """Consolidated positions table (household / person overview)."""
    if currency_overrides is None:
        currency_overrides = {}
    totals = dict(mkt_val_cad=0.0, mkt_val_usd=0.0, pnl_cad=0.0, pnl_usd=0.0)

    if df.empty:
        return "<p>No positions.</p>", totals

    stocks = df[df["Asset Class"].str.upper() != "OPT"].copy() if "Asset Class" in df.columns else df.copy()

    if total_mv_with_cash is None:
        total_mv_cad = sum(
            conv_cad(r.get("Market Value"),
                     get_currency(str(r.get("Equity Symbol", "")).strip(),
                                  str(r.get("Currency", "CAD")), currency_overrides), fx)
            for _, r in stocks.iterrows()
        )
        if balances is not None and not balances.empty:
            for _, r in balances.iterrows():
                cash_cad = safe_float(r.get("Cash in CAD Combined")) or 0.0
                cash_usd = safe_float(r.get("Cash in USD")) or 0.0
                total_mv_cad += cash_cad + (cash_usd * fx)
    else:
        total_mv_cad = total_mv_with_cash

    rows = []
    asset_counts = {}

    for _, r in stocks.iterrows():
        symbol    = str(r.get("Equity Symbol", "")).strip()
        ccy       = get_currency(symbol, str(r.get("Currency", "CAD")), currency_overrides)
        asset_cls = str(r.get("Asset Class", ""))
        accounts  = r.get("_accounts", [])
        accounts_str = ", ".join(accounts) if isinstance(accounts, list) else ""

        sectors = sector_data.get(symbol, {})
        if sectors:
            sector = "Multi-Sector ETF" if len(sectors) > 1 else next(iter(sectors.keys()))
        else:
            sector = "Unknown"

        mv_cad = conv_cad(r.get("Market Value"), ccy, fx)
        mv_usd = conv_usd(r.get("Market Value"), ccy, fx)
        p_cad  = conv_cad(r.get("Profit And Loss"), ccy, fx)
        p_usd  = conv_usd(r.get("Profit And Loss"), ccy, fx)

        alloc_pct = (mv_cad / total_mv_cad * 100) if total_mv_cad > 0 else 0.0
        alloc_cls = "num alloc-warn" if alloc_pct > 10 else "num"

        totals["mkt_val_cad"] += mv_cad
        totals["mkt_val_usd"] += mv_usd
        totals["pnl_cad"]     += p_cad
        totals["pnl_usd"]     += p_usd
        asset_counts[asset_cls] = asset_counts.get(asset_cls, 0) + 1
        row_cls = ' class="etf-row"' if asset_cls.upper() == "ETF" else ""

        mp      = safe_float(r.get("Market Price")) or 0.0
        cs      = safe_float(r.get("Cost Per Share")) or 0.0
        pnl_pct = ((mp - cs) / cs * 100) if cs > 0 else 0.0

        rows.append(
            f"<tr{row_cls}>"
            f"<td><strong>{symbol}</strong></td>"
            f'<td title="{r.get("Equity Description","")}">{r.get("Equity Description","")}</td>'
            f"<td>{sector}</td>"
            f"<td>{asset_cls}</td>"
            f"<td>{ccy}</td>"
            f"<td>{accounts_str}</td>"
            f'<td class="num">{fmt_qty(r.get("Quantity",""))}</td>'
            + money_td_native(mv_cad if str(ccy).upper() == "CAD" else mv_usd, ccy)
            + money_td_native(p_cad  if str(ccy).upper() == "CAD" else p_usd,  ccy, pnl=True)
            + f'<td class="num {pnl_class(pnl_pct)}">{fmt_pct(pnl_pct)}</td>'
            + f'<td class="{alloc_cls}">{alloc_pct:.1f}%</td>'
            + "</tr>"
        )

    asset_summary = " + ".join(f"{count} {cls}" for cls, count in sorted(asset_counts.items()))
    summary_html  = f'<div class="asset-summary"><strong>Holdings:</strong> {asset_summary}</div>'

    tbl = (
        summary_html
        + '<table class="pos-tbl">'
        + "<colgroup>"
        + '<col style="width:5%"><col style="width:18%"><col style="width:9%">'
        + '<col style="width:7%"><col style="width:7%"><col style="width:16%">'
        + '<col style="width:8%"><col style="width:5%"><col style="width:5%">'
        + '<col style="width:4%"><col style="width:4%"><col style="width:5%"><col style="width:2%">'
        + "</colgroup>"
        + "<thead><tr>"
        + "<th>Symbol</th><th>Description</th><th>Sector</th><th>Class</th>"
        + "<th>Type</th><th>Accounts</th>"
        + '<th class="num">Qty</th>'
        + money_th_native("Mkt Val")
        + money_th_native("P&L")
        + '<th class="num">P&amp;L %</th>'
        + '<th class="num">Alloc %</th>'
        + "</tr></thead>"
        + f"<tbody>{''.join(rows)}</tbody>"
        + "</table>"
    )
    return tbl, totals


def positions_table(df: pd.DataFrame, fx: float, sector_data: dict,
                    balances: pd.DataFrame = None, acct_num: str = None,
                    currency_overrides: dict = None):
    """Single-account positions table."""
    if currency_overrides is None:
        currency_overrides = {}
    totals = dict(mkt_val_cad=0.0, mkt_val_usd=0.0, pnl_cad=0.0, pnl_usd=0.0)

    if df.empty:
        return "<p>No positions.</p>", totals

    stocks  = df[df["Asset Class"].str.upper() != "OPT"].copy() if "Asset Class" in df.columns else df.copy()
    options = df[df["Asset Class"].str.upper() == "OPT"].copy() if "Asset Class" in df.columns else pd.DataFrame()

    total_mv_cad = sum(
        conv_cad(r.get("Market Value"),
                 get_currency(str(r.get("Equity Symbol", "")).strip(),
                              str(r.get("Currency", "CAD")), currency_overrides), fx)
        for _, r in df.iterrows()
    )

    if balances is not None and not balances.empty:
        for _, r in balances.iterrows():
            if acct_num:
                acct = str(int(r.get("Account Number", 0))) if pd.notna(r.get("Account Number")) else ""
                if acct != acct_num:
                    continue
            cash_cad = safe_float(r.get("Cash in CAD Combined")) or 0.0
            cash_usd = safe_float(r.get("Cash in USD")) or 0.0
            total_mv_cad += cash_cad + (cash_usd * fx)

    rows = []
    asset_counts = {}
    for _, r in stocks.iterrows():
        symbol    = str(r.get("Equity Symbol", "")).strip()
        ccy       = get_currency(symbol, str(r.get("Currency", "CAD")), currency_overrides)
        asset_cls = str(r.get("Asset Class", ""))
        sectors   = sector_data.get(symbol, {})
        sector    = ("Multi-Sector ETF" if len(sectors) > 1 else next(iter(sectors.keys()))) if sectors else "Unknown"

        mv_cad = conv_cad(r.get("Market Value"),    ccy, fx)
        mv_usd = conv_usd(r.get("Market Value"),    ccy, fx)
        p_cad  = conv_cad(r.get("Profit And Loss"), ccy, fx)
        p_usd  = conv_usd(r.get("Profit And Loss"), ccy, fx)
        cs_cad = conv_cad(r.get("Cost Per Share"),  ccy, fx)
        cs_usd = conv_usd(r.get("Cost Per Share"),  ccy, fx)
        mp_cad = conv_cad(r.get("Market Price"),    ccy, fx)
        mp_usd = conv_usd(r.get("Market Price"),    ccy, fx)

        alloc_pct = (mv_cad / total_mv_cad * 100) if total_mv_cad > 0 else 0.0
        alloc_cls = "num alloc-warn" if alloc_pct > 10 else "num"

        totals["mkt_val_cad"] += mv_cad
        totals["mkt_val_usd"] += mv_usd
        totals["pnl_cad"]     += p_cad
        totals["pnl_usd"]     += p_usd
        asset_counts[asset_cls] = asset_counts.get(asset_cls, 0) + 1
        row_cls = ' class="etf-row"' if asset_cls.upper() == "ETF" else ""

        cost_per_share = safe_float(r.get("Cost Per Share")) or 0.0
        mp = mp_usd if str(ccy).upper() == "USD" else mp_cad
        pnl_pct = ((mp - cost_per_share) / cost_per_share * 100) if cost_per_share > 0 else 0.0

        native_cs = cs_usd if str(ccy).upper() == "USD" else cs_cad
        native_mp = mp_usd if str(ccy).upper() == "USD" else mp_cad
        native_mv = mv_usd if str(ccy).upper() == "USD" else mv_cad
        native_p  = p_usd  if str(ccy).upper() == "USD" else p_cad

        rows.append(
            f"<tr{row_cls}>"
            f"<td><strong>{symbol}</strong></td>"
            f'<td title="{r.get("Equity Description","")}">{r.get("Equity Description","")}</td>'
            f"<td>{sector}</td>"
            f"<td>{asset_cls}</td>"
            f"<td>{ccy}</td>"
            f'<td class="num">{fmt_qty(r.get("Quantity",""))}</td>'
            + money_td_native(native_cs, ccy)
            + money_td_native(native_mp, ccy)
            + money_td_native(native_mv, ccy)
            + money_td_native(native_p,  ccy, pnl=True)
            + f'<td class="num {pnl_class(pnl_pct)}">{fmt_pct(pnl_pct)}</td>'
            + f'<td class="{alloc_cls}">{alloc_pct:.1f}%</td>'
            + "</tr>"
        )

    tbl = (
        '<table class="pos-tbl">'
        "<thead><tr>"
        "<th>Symbol</th><th>Description</th><th>Sector</th><th>Class</th><th>Type</th>"
        '<th class="num">Qty</th>'
        + money_th_native("Cost/Sh")
        + money_th_native("Mkt Price")
        + money_th_native("Mkt Val")
        + money_th_native("P&amp;L")
        + '<th class="num">P&amp;L %</th>'
        + '<th class="num">Alloc %</th>'
        + "</tr></thead>"
        + f"<tbody>{''.join(rows)}</tbody>"
        + "</table>"
    )

    if not options.empty:
        opt_t = dict(mkt_val_cad=0.0, mkt_val_usd=0.0, pnl_cad=0.0, pnl_usd=0.0)
        opt_rows = []
        for _, r in options.iterrows():
            symbol = str(r.get("Equity Symbol", "")).strip()
            ccy    = get_currency(symbol, str(r.get("Currency", "CAD")), currency_overrides)
            mv_cad = conv_cad(r.get("Market Value"),    ccy, fx)
            mv_usd = conv_usd(r.get("Market Value"),    ccy, fx)
            p_cad  = conv_cad(r.get("Profit And Loss"), ccy, fx)
            p_usd  = conv_usd(r.get("Profit And Loss"), ccy, fx)
            opt_alloc_pct = (mv_cad / total_mv_cad * 100) if total_mv_cad > 0 else 0.0
            opt_alloc_cls = "num alloc-warn" if opt_alloc_pct > 10 else "num"
            opt_t["mkt_val_cad"] += mv_cad; opt_t["mkt_val_usd"] += mv_usd
            opt_t["pnl_cad"]     += p_cad;  opt_t["pnl_usd"]     += p_usd
            totals["mkt_val_cad"] += mv_cad; totals["mkt_val_usd"] += mv_usd
            totals["pnl_cad"]     += p_cad;  totals["pnl_usd"]     += p_usd

            opt_mp      = safe_float(r.get("Market Price")) or 0.0
            opt_cs      = safe_float(r.get("Cost Per Share")) or 0.0
            opt_pnl_pct = ((opt_mp - opt_cs) / opt_cs * 100) if opt_cs > 0 else 0.0

            native_mv_opt = mv_usd if str(ccy).upper() == "USD" else mv_cad
            native_p_opt  = p_usd  if str(ccy).upper() == "USD" else p_cad
            opt_rows.append(
                "<tr>"
                f"<td><strong>{r.get('Equity Symbol','')}</strong></td>"
                f'<td title="{r.get("Equity Description","")}">{r.get("Equity Description","")}</td>'
                f"<td>{ccy}</td>"
                f'<td class="num">{fmt_qty(r.get("Quantity",""))}</td>'
                + money_td_native(native_mv_opt, ccy)
                + money_td_native(native_p_opt,  ccy, pnl=True)
                + f'<td class="num {pnl_class(opt_pnl_pct)}">{fmt_pct(opt_pnl_pct)}</td>'
                + f'<td class="{opt_alloc_cls}">{opt_alloc_pct:.1f}%</td>'
                + "</tr>"
            )
        o_pc = pnl_class(opt_t["pnl_cad"])
        tbl += (
            '<details style="margin-top:12px">'
            f'<summary><strong>Options ({len(options)} contracts)'
            f' — P&amp;L: <span class="{o_pc} money">'
            f'{fmt_cad(opt_t["pnl_cad"])} / {fmt_usd(opt_t["pnl_usd"])}</span></strong></summary>'
            '<table style="margin-top:8px"><thead><tr>'
            "<th>Symbol</th><th>Description</th><th>CCY</th>"
            '<th class="num">Qty</th>'
            + money_th_native("Mkt Val")
            + money_th_native("P&amp;L")
            + '<th class="num">P&amp;L %</th>'
            + '<th class="num">Alloc %</th>'
            + "</tr></thead>"
            + f"<tbody>{''.join(opt_rows)}</tbody>"
            + "</table></details>"
        )

    asset_summary = " + ".join(f"{count} {cls}" for cls, count in sorted(asset_counts.items()))
    summary_html  = f'<div class="asset-summary"><strong>Holdings:</strong> {asset_summary}</div>'
    tbl = summary_html + tbl
    return tbl, totals


# ---------------------------------------------------------------------------
# Balance section
# ---------------------------------------------------------------------------

def balances_section(balances: pd.DataFrame, acct_nums: list,
                     positions: pd.DataFrame = None, fx: float = 1.0,
                     currency_overrides: dict = None) -> str:
    if balances.empty:
        return "<p>No balance data.</p>"
    if currency_overrides is None:
        currency_overrides = {}

    rows = []
    t = dict(combined_cad_cash=0.0, combined_usd_cash=0.0,
             combined_cad_mv=0.0,   combined_usd_mv=0.0,
             combined_cad_eq=0.0,   combined_usd_eq=0.0,
             cad_cash=0.0, usd_cash=0.0, cad_mv=0.0, usd_mv=0.0,
             cad_eq=0.0,   usd_eq=0.0,
             combined_cad_pnl=0.0, combined_usd_pnl=0.0,
             cad_pnl=0.0,  usd_pnl=0.0)

    for _, r in balances.iterrows():
        acct = str(int(r.get("Account Number", 0)))
        if acct_nums and acct not in acct_nums:
            continue

        combined_cad_cash = safe_float(r.get("Cash in CAD Combined")) or 0.0
        combined_usd_cash = safe_float(r.get("Cash in USD Combined")) or 0.0
        combined_cad_mv   = safe_float(r.get("Market Valuein CAD Combined")) or 0.0
        combined_usd_mv   = safe_float(r.get("Market Value in USD Combined")) or 0.0
        combined_cad_eq   = safe_float(r.get("Total Equity in CAD Combined")) or 0.0
        combined_usd_eq   = safe_float(r.get("Total Equity in USD Combined")) or 0.0
        cad_cash = safe_float(r.get("Cash in CAD Native")) or 0.0
        usd_cash = safe_float(r.get("Cash in USD Native")) or 0.0
        cad_mv   = safe_float(r.get("Market Value in CAD Native")) or 0.0
        usd_mv   = safe_float(r.get("Market Value in USD Native")) or 0.0
        cad_eq   = safe_float(r.get("Total Equity in CAD Native")) or 0.0
        usd_eq   = safe_float(r.get("Total Equity in USD Native")) or 0.0

        combined_cad_pnl = combined_usd_pnl = cad_pnl = usd_pnl = 0.0
        if positions is not None and not positions.empty:
            acct_pos = positions[
                positions["Account Number"].apply(lambda x: str(int(x)) if pd.notna(x) else "") == acct
            ]
            for _, p in acct_pos.iterrows():
                p_val = safe_float(p.get("Profit And Loss")) or 0.0
                ccy   = get_currency(str(p.get("Equity Symbol", "")).strip(),
                                     str(p.get("Currency", "CAD")), currency_overrides)
                p_cad = conv_cad(p_val, ccy, fx)
                p_usd = conv_usd(p_val, ccy, fx)
                combined_cad_pnl += p_cad
                combined_usd_pnl += p_usd
                if ccy.upper() == "CAD":
                    cad_pnl += p_cad
                else:
                    usd_pnl += p_usd

        cost_basis = combined_cad_eq - combined_cad_pnl
        pnl_pct    = (combined_cad_pnl / cost_basis * 100) if cost_basis != 0 else 0.0

        t["combined_cad_cash"] += combined_cad_cash; t["combined_usd_cash"] += combined_usd_cash
        t["combined_cad_mv"]   += combined_cad_mv;   t["combined_usd_mv"]   += combined_usd_mv
        t["combined_cad_eq"]   += combined_cad_eq;   t["combined_usd_eq"]   += combined_usd_eq
        t["combined_cad_pnl"]  += combined_cad_pnl;  t["combined_usd_pnl"]  += combined_usd_pnl
        t["cad_cash"] += cad_cash; t["usd_cash"] += usd_cash
        t["cad_mv"]   += cad_mv;   t["usd_mv"]   += usd_mv
        t["cad_eq"]   += cad_eq;   t["usd_eq"]   += usd_eq
        t["cad_pnl"]  += cad_pnl;  t["usd_pnl"]  += usd_pnl

        compact  = len(acct_nums) == 1
        acct_cols = "" if compact else f"<td>{account_label(acct)}</td><td>{r.get('Account Type','')}</td>"
        rows.append(
            "<tr>"
            + acct_cols
            + money_td_multiview(combined_cad_cash, combined_usd_cash, cad_cash, usd_cash)
            + money_td_multiview(combined_cad_mv, combined_usd_mv, cad_mv, usd_mv)
            + money_td_multiview(combined_cad_pnl, combined_usd_pnl, cad_pnl, usd_pnl, pnl=True)
            + f'<td class="num {pnl_class(pnl_pct)}">{fmt_pct(pnl_pct)}</td>'
            + money_td_multiview(combined_cad_eq, combined_usd_eq, cad_eq, usd_eq)
            + "</tr>"
        )

    total_cost_basis = t["combined_cad_eq"] - t["combined_cad_pnl"]
    total_pnl_pct    = (t["combined_cad_pnl"] / total_cost_basis * 100) if total_cost_basis != 0 else 0.0
    pnl_bg = "background:#d4edda" if t["combined_cad_pnl"] >= 0 else "background:#f8d7da"

    compact    = len(acct_nums) == 1
    acct_th    = "" if compact else "<th>Account</th><th>Type</th>"
    tfoot      = "" if compact else (
        f"<tfoot><tr style='{pnl_bg}'>"
        + "<td colspan='2'>Total</td>"
        + money_td_multiview(t["combined_cad_cash"], t["combined_usd_cash"], t["cad_cash"], t["usd_cash"])
        + money_td_multiview(t["combined_cad_mv"],   t["combined_usd_mv"],   t["cad_mv"],   t["usd_mv"])
        + money_td_multiview(t["combined_cad_pnl"],  t["combined_usd_pnl"],  t["cad_pnl"],  t["usd_pnl"], pnl=True)
        + f'<td class="num {pnl_class(total_pnl_pct)}">{fmt_pct(total_pnl_pct)}</td>'
        + money_td_multiview(t["combined_cad_eq"], t["combined_usd_eq"], t["cad_eq"], t["usd_eq"])
        + "</tr></tfoot>"
    )

    btn_style = "font-weight:{fw};border:{br};background-color:{bg};padding:8px 12px;cursor:pointer;color:#000;font-size:14px"

    def _btn(view, label, active=False):
        fw = "bold" if active else "normal"
        br = "2px solid green" if active else "1px solid #ccc"
        bg = "rgba(0,128,0,0.1)" if active else "white"
        return f'<button class="ccy-btn" data-view="{view}" onclick="switchView(\'{view}\')" style="font-weight:{fw};border:{br};background-color:{bg};padding:8px 12px;cursor:pointer;color:#000;font-size:14px">{label}</button>'

    return (
        '<div style="margin-bottom:1rem">'
        + _btn("combined-cad", "Combined in CAD", active=True) + " "
        + _btn("combined-usd", "Combined in USD") + " "
        + _btn("cad",          "CAD") + " "
        + _btn("usd",          "USD")
        + "</div>"
        + ('<table class="bal-tbl" style="width:auto;min-width:0">' if compact else '<table class="bal-tbl">')
        + "<thead><tr>"
        + acct_th
        + money_th("Cash (CAD)",    "Cash (USD)")
        + money_th("Mkt Val (CAD)", "Mkt Val (USD)")
        + money_th("P&amp;L (CAD)", "P&amp;L (USD)")
        + '<th class="num">P&amp;L %</th>'
        + money_th("Equity (CAD)", "Equity (USD)")
        + "</tr></thead>"
        + f"<tbody>{''.join(rows)}</tbody>"
        + tfoot
        + "</table>"
    )


# ---------------------------------------------------------------------------
# Allocation bars
# ---------------------------------------------------------------------------

def allocation_bars(alloc_df: pd.DataFrame) -> str:
    if alloc_df is None or alloc_df.empty:
        return ""
    cols     = alloc_df.columns.tolist()
    name_col = cols[0]
    pct_col  = next((c for c in cols if "%" in str(c) or "pct" in str(c).lower()), cols[1])
    colors   = {
        "STK": "#4e79a7", "Stocks": "#4e79a7",
        "ETF": "#59a14f", "ETFs":   "#59a14f",
        "Cash": "#f28e2b",
        "ADR":  "#9c755f",
        "OPT":  "#e15759",
    }
    bars = []
    for _, r in alloc_df.iterrows():
        name = str(r[name_col])
        try:
            pct = float(str(r[pct_col]).replace("%", "").strip())
        except (ValueError, TypeError):
            continue
        color = colors.get(name, "#76b7b2")
        bars.append(
            '<div class="bar-row">'
            f'<span class="bar-label">{name}</span>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{min(pct,100):.1f}%;background:{color}"></div></div>'
            f'<span class="bar-pct">{pct:.1f}%</span>'
            "</div>"
        )
    return f'<div class="alloc-bars">{"".join(bars)}</div>'


def sector_bars(sector_totals: dict, total_mv: float, unknown_tickers: list) -> str:
    if not sector_totals or total_mv == 0:
        return ""
    items = sorted([(s, v) for s, v in sector_totals.items() if s != "Unknown"],
                   key=lambda x: x[1], reverse=True)
    if "Unknown" in sector_totals:
        items.append(("Unknown", sector_totals["Unknown"]))
    bars = []
    for sector, value in items:
        pct    = value / total_mv * 100
        color  = SECTOR_COLORS.get(sector, "#aaa")
        suffix = (f' <span class="unknown-tickers">({", ".join(unknown_tickers)})</span>'
                  if sector == "Unknown" and unknown_tickers else "")
        bars.append(
            '<div class="bar-row">'
            f'<span class="bar-label-wide">{sector}{suffix}</span>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{min(pct,100):.1f}%;background:{color}"></div></div>'
            f'<span class="bar-pct">{pct:.1f}%</span>'
            "</div>"
        )
    return f'<div class="alloc-bars">{"".join(bars)}</div>'


def subsector_bars(subsector_totals: dict, total_mv: float) -> str:
    if not subsector_totals or total_mv == 0:
        return ""
    items = sorted(subsector_totals.items(), key=lambda x: x[1], reverse=True)
    bars  = []
    for subsector, value in items:
        pct = value / total_mv * 100
        bars.append(
            '<div class="bar-row subsector-row">'
            f'<span class="bar-label-subsector">{subsector}</span>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{min(pct,100):.1f}%;background:#b8b8d8"></div></div>'
            f'<span class="bar-pct">{pct:.1f}%</span>'
            "</div>"
        )
    return (
        '<div class="alloc-bars subsector-bars">'
        '<div style="font-size:11px;color:#666;margin-bottom:8px;font-weight:600;">Subsector Breakdown:</div>'
        + "".join(bars)
        + "</div>"
    )


# ---------------------------------------------------------------------------
# Summary cards
# ---------------------------------------------------------------------------

def summary_cards(eq_cad: float, eq_usd: float, pnl_cad: float, pnl_usd: float) -> str:
    pc = pnl_class(pnl_cad)
    return (
        '<div class="summary-grid">'
        '<div class="summary-card">'
        "<div class='card-label'>Total Equity</div>"
        f'<div class="card-value money">{fmt_cad(eq_cad)} / {fmt_usd(eq_usd)}</div>'
        "</div>"
        '<div class="summary-card">'
        "<div class='card-label'>Total P&amp;L</div>"
        f'<div class="card-value {pc} money">{fmt_cad(pnl_cad)} / {fmt_usd(pnl_usd)}</div>'
        "</div>"
        "</div>"
    )


def _hh_card(label: str, cad_val: float, usd_val: float, extra_class: str = "") -> str:
    is_pnl   = "P&" in label
    pc       = pnl_class(cad_val) if is_pnl else ""
    card_cls = " ".join(c for c in ["summary-card", extra_class, pc] if c)
    return (
        f'<div class="{card_cls}">'
        f"<div class='card-label'>{label}</div>"
        f'<div class="card-value money">{fmt_cad(cad_val)} / {fmt_usd(usd_val)}</div>'
        "</div>"
    )


# ---------------------------------------------------------------------------
# Person tabs
# ---------------------------------------------------------------------------

def person_tabs(name: str, data: dict, person_id: str,
                sector_data: dict, subsector_data: dict,
                currency_overrides: dict = None):
    """Returns (html, person_totals_dict)."""
    if currency_overrides is None:
        currency_overrides = {}
    balances  = data.get("Balances", pd.DataFrame())
    positions = data.get("Positions", pd.DataFrame())
    alloc     = data.get("AllocationsOwnedSD", pd.DataFrame())
    fx        = get_fx(data)

    acct_nums = (
        [str(int(a)) for a in balances["Account Number"].dropna()]
        if not balances.empty and "Account Number" in balances.columns else []
    )
    eq_cad = float(balances["Total Equity in CAD Combined"].sum()) if not balances.empty and "Total Equity in CAD Combined" in balances.columns else 0.0
    eq_usd = float(balances["Total Equity in USD"].sum())          if not balances.empty and "Total Equity in USD"           in balances.columns else 0.0

    tabs_html, panels_html = [], []

    # All Accounts tab
    tab_id = f"{person_id}_all"
    positions_consolidated = consolidate_positions(positions, person_label=name)
    all_tbl, all_totals = consolidated_positions_table(
        positions_consolidated, fx, sector_data, subsector_data, balances, None, currency_overrides)
    tabs_html.append(
        f'<button class="subtab active" onclick="showSubtab(this,\'{tab_id}\')">All Accounts</button>')
    s_all, s_all_unk, s_all_mv = compute_sector_alloc(
        positions, sector_data, fx, balances, [], currency_overrides)
    ss_all, ss_all_mv = compute_subsector_alloc(
        positions, sector_data, subsector_data, fx, balances, [], currency_overrides)
    panels_html.append(
        f'<div id="{tab_id}" class="subpanel active">'
        + "<h3>Balances</h3>"
        + balances_section(balances, [], positions, fx, currency_overrides)
        + "<h3>Asset Allocation</h3>"
        + allocation_bars(alloc)
        + "<h3>Positions</h3>"
        + all_tbl
        + "<h3>Sector Allocation</h3>"
        + sector_bars(s_all, s_all_mv, s_all_unk)
        + subsector_bars(ss_all, ss_all_mv)
        + '<div class="legend-note"><strong>Note:</strong> Sector allocation reflects underlying ETF holdings. Multi-sector ETFs are distributed across their component sectors by weight.</div>'
        + "</div>"
    )

    # Per-account tabs
    for acct in acct_nums:
        tab_id = f"{person_id}_{acct}"
        tabs_html.append(
            f'<button class="subtab" onclick="showSubtab(this,\'{tab_id}\')">{account_label(acct)}</button>')

        acct_pos = (
            positions[positions["Account Number"].apply(
                lambda x: str(int(x)) if pd.notna(x) else "") == acct].copy()
            if not positions.empty and "Account Number" in positions.columns
            else pd.DataFrame()
        )
        acct_tbl, _ = positions_table(acct_pos, fx, sector_data, balances, acct, currency_overrides)

        s_acct, s_acct_unk, s_acct_mv = compute_sector_alloc(
            acct_pos, sector_data, fx, balances, [acct], currency_overrides)
        ss_acct, ss_acct_mv = compute_subsector_alloc(
            acct_pos, sector_data, subsector_data, fx, balances, [acct], currency_overrides)
        panels_html.append(
            f'<div id="{tab_id}" class="subpanel">'
            + "<h3>Balance</h3>"
            + balances_section(balances, [acct], positions, fx, currency_overrides)
            + "<h3>Positions</h3>"
            + acct_tbl
            + "<h3>Sector Allocation</h3>"
            + sector_bars(s_acct, s_acct_mv, s_acct_unk)
            + subsector_bars(ss_acct, ss_acct_mv)
            + "</div>"
        )

    html = f'<div class="subtab-bar">{"".join(tabs_html)}</div>' + "".join(panels_html)
    return html, dict(eq_cad=eq_cad, eq_usd=eq_usd,
                      pnl_cad=all_totals["pnl_cad"], pnl_usd=all_totals["pnl_usd"])


# ---------------------------------------------------------------------------
# Household components
# ---------------------------------------------------------------------------

def _combined_balance_table(chandu_data: dict, nandu_data: dict,
                             currency_overrides: dict = None) -> str:
    if currency_overrides is None:
        currency_overrides = {}
    rows = []
    t = dict(combined_cad_cash=0.0, combined_usd_cash=0.0,
             combined_cad_mv=0.0,   combined_usd_mv=0.0,
             combined_cad_eq=0.0,   combined_usd_eq=0.0,
             cad_cash=0.0, usd_cash=0.0, cad_mv=0.0, usd_mv=0.0,
             cad_eq=0.0,   usd_eq=0.0,
             combined_cad_pnl=0.0, combined_usd_pnl=0.0,
             cad_pnl=0.0,  usd_pnl=0.0)

    for person, data in [("Chandu", chandu_data), ("Nandu", nandu_data)]:
        bal = data.get("Balances", pd.DataFrame())
        if bal.empty:
            continue
        pos = data.get("Positions", pd.DataFrame())
        fx  = get_fx(data)
        for _, r in bal.iterrows():
            acct = str(int(r.get("Account Number", 0)))

            combined_cad_cash = safe_float(r.get("Cash in CAD Combined")) or 0.0
            combined_usd_cash = safe_float(r.get("Cash in USD Combined")) or 0.0
            combined_cad_mv   = safe_float(r.get("Market Valuein CAD Combined")) or 0.0
            combined_usd_mv   = safe_float(r.get("Market Value in USD Combined")) or 0.0
            combined_cad_eq   = safe_float(r.get("Total Equity in CAD Combined")) or 0.0
            combined_usd_eq   = safe_float(r.get("Total Equity in USD Combined")) or 0.0
            cad_cash = safe_float(r.get("Cash in CAD Native")) or 0.0
            usd_cash = safe_float(r.get("Cash in USD Native")) or 0.0
            cad_mv   = safe_float(r.get("Market Value in CAD Native")) or 0.0
            usd_mv   = safe_float(r.get("Market Value in USD Native")) or 0.0
            cad_eq   = safe_float(r.get("Total Equity in CAD Native")) or 0.0
            usd_eq   = safe_float(r.get("Total Equity in USD Native")) or 0.0

            combined_cad_pnl = combined_usd_pnl = cad_pnl = usd_pnl = 0.0
            if not pos.empty:
                acct_pos = pos[
                    pos["Account Number"].apply(lambda x: str(int(x)) if pd.notna(x) else "") == acct
                ]
                for _, p in acct_pos.iterrows():
                    p_val = safe_float(p.get("Profit And Loss")) or 0.0
                    ccy   = get_currency(str(p.get("Equity Symbol", "")).strip(),
                                         str(p.get("Currency", "CAD")), currency_overrides)
                    p_cad = conv_cad(p_val, ccy, fx)
                    p_usd = p_val if ccy.upper() == "USD" else p_cad / fx
                    combined_cad_pnl += p_cad
                    combined_usd_pnl += p_usd
                    if ccy.upper() == "CAD":
                        cad_pnl += p_cad
                    else:
                        usd_pnl += p_usd

            for k, v in [("combined_cad_cash", combined_cad_cash), ("combined_usd_cash", combined_usd_cash),
                          ("combined_cad_mv",   combined_cad_mv),   ("combined_usd_mv",   combined_usd_mv),
                          ("combined_cad_eq",   combined_cad_eq),   ("combined_usd_eq",   combined_usd_eq),
                          ("combined_cad_pnl",  combined_cad_pnl),  ("combined_usd_pnl",  combined_usd_pnl),
                          ("cad_cash", cad_cash), ("usd_cash", usd_cash),
                          ("cad_mv",   cad_mv),   ("usd_mv",   usd_mv),
                          ("cad_eq",   cad_eq),   ("usd_eq",   usd_eq),
                          ("cad_pnl",  cad_pnl),  ("usd_pnl",  usd_pnl)]:
                t[k] += v

            cost_basis = combined_cad_eq - combined_cad_pnl
            pnl_pct    = (combined_cad_pnl / cost_basis * 100) if cost_basis != 0 else 0.0
            rows.append(
                "<tr>"
                f"<td>{person}</td>"
                f"<td>{account_label(acct)}</td>"
                f"<td>{r.get('Account Type','')}</td>"
                + money_td_multiview(combined_cad_cash, combined_usd_cash, cad_cash, usd_cash)
                + money_td_multiview(combined_cad_mv,   combined_usd_mv,   cad_mv,   usd_mv)
                + money_td_multiview(combined_cad_pnl,  combined_usd_pnl,  cad_pnl,  usd_pnl, pnl=True)
                + f'<td class="num {pnl_class(pnl_pct)}">{fmt_pct(pnl_pct)}</td>'
                + money_td_multiview(combined_cad_eq, combined_usd_eq, cad_eq, usd_eq)
                + "</tr>"
            )

    total_cost_basis = t["combined_cad_eq"] - t["combined_cad_pnl"]
    total_pnl_pct    = (t["combined_cad_pnl"] / total_cost_basis * 100) if total_cost_basis != 0 else 0.0
    pnl_bg = "background:#d4edda" if t["combined_cad_pnl"] >= 0 else "background:#f8d7da"

    def _btn(view, label, active=False):
        fw = "bold" if active else "normal"
        br = "2px solid green" if active else "1px solid #ccc"
        bg = "rgba(0,128,0,0.1)" if active else "white"
        return f'<button class="ccy-btn" data-view="{view}" onclick="switchView(\'{view}\')" style="font-weight:{fw};border:{br};background-color:{bg};padding:8px 12px;cursor:pointer;color:#000;font-size:14px">{label}</button>'

    return (
        '<div style="margin-bottom:1rem">'
        + _btn("combined-cad", "Combined in CAD", active=True) + " "
        + _btn("combined-usd", "Combined in USD") + " "
        + _btn("cad", "CAD") + " "
        + _btn("usd", "USD")
        + "</div>"
        + "<table>"
        + "<thead><tr>"
        + "<th>Person</th><th>Account</th><th>Type</th>"
        + money_th("Cash (CAD)",    "Cash (USD)")
        + money_th("Mkt Val (CAD)", "Mkt Val (USD)")
        + money_th("P&amp;L (CAD)", "P&amp;L (USD)")
        + '<th class="num">P&amp;L %</th>'
        + money_th("Equity (CAD)", "Equity (USD)")
        + "</tr></thead>"
        + f"<tbody>{''.join(rows)}</tbody>"
        + f"<tfoot><tr style='{pnl_bg}'>"
        + "<td colspan='3'>Total</td>"
        + money_td_multiview(t["combined_cad_cash"], t["combined_usd_cash"], t["cad_cash"], t["usd_cash"])
        + money_td_multiview(t["combined_cad_mv"],   t["combined_usd_mv"],   t["cad_mv"],   t["usd_mv"])
        + money_td_multiview(t["combined_cad_pnl"],  t["combined_usd_pnl"],  t["cad_pnl"],  t["usd_pnl"], pnl=True)
        + f'<td class="num {pnl_class(total_pnl_pct)}">{fmt_pct(total_pnl_pct)}</td>'
        + money_td_multiview(t["combined_cad_eq"], t["combined_usd_eq"], t["cad_eq"], t["usd_eq"])
        + "</tr></tfoot>"
        + "</table>"
    )


def _household_sector_bars(chandu_data: dict, nandu_data: dict,
                            sector_data: dict, subsector_data: dict,
                            currency_overrides: dict = None) -> str:
    if currency_overrides is None:
        currency_overrides = {}
    fx  = get_fx(chandu_data)
    cp  = chandu_data.get("Positions", pd.DataFrame())
    np_ = nandu_data.get("Positions", pd.DataFrame())
    cb  = chandu_data.get("Balances", pd.DataFrame())
    nb  = nandu_data.get("Balances", pd.DataFrame())
    combined_pos = pd.concat([cp, np_], ignore_index=True) if not cp.empty or not np_.empty else pd.DataFrame()
    combined_bal = pd.concat([cb, nb], ignore_index=True) if not cb.empty or not nb.empty else pd.DataFrame()
    s, unk, mv = compute_sector_alloc(combined_pos, sector_data, fx, combined_bal, [], currency_overrides)
    ss, ss_mv  = compute_subsector_alloc(combined_pos, sector_data, subsector_data, fx, combined_bal, [], currency_overrides)
    return sector_bars(s, mv, unk) + subsector_bars(ss, ss_mv)


def household_tab(chandu_data: dict, nandu_data: dict, ch: dict, nd: dict,
                  sector_data: dict, subsector_data: dict,
                  currency_overrides: dict = None) -> str:
    if currency_overrides is None:
        currency_overrides = {}

    cp  = chandu_data.get("Positions", pd.DataFrame())
    np_ = nandu_data.get("Positions",  pd.DataFrame())
    cb  = chandu_data.get("Balances", pd.DataFrame())
    nb  = nandu_data.get("Balances", pd.DataFrame())

    shared_html = ""
    if not cp.empty and not np_.empty and "Equity Symbol" in cp.columns and "Equity Symbol" in np_.columns:
        filt = lambda d: (d[d["Asset Class"].str.upper() != "OPT"]["Equity Symbol"].dropna()
                          if "Asset Class" in d.columns else d["Equity Symbol"].dropna())
        both = sorted(set(filt(cp)) & set(filt(np_)))
        if both:
            shared_html = f'<p style="margin:12px 0"><strong>Shared holdings:</strong> {", ".join(both)}</p>'

    cp_p = cp.copy(); cp_p["_person"] = "Chandu"
    np_p = np_.copy(); np_p["_person"] = "Nandu"
    combined_pos = pd.concat([cp_p, np_p], ignore_index=True) if not cp.empty or not np_.empty else pd.DataFrame()
    combined_bal = pd.concat([cb, nb], ignore_index=True) if not cb.empty or not nb.empty else pd.DataFrame()
    combined_pos_consolidated = consolidate_positions(combined_pos)

    fx = get_fx(chandu_data)
    hh_total_mv = sum(
        conv_cad(r.get("Market Value"),
                 get_currency(str(r.get("Equity Symbol", "")).strip(),
                              str(r.get("Currency", "CAD")), currency_overrides), fx)
        for _, r in combined_pos.iterrows()
    )
    for bal_df in [cb, nb]:
        if not bal_df.empty:
            for _, r in bal_df.iterrows():
                cash_cad = safe_float(r.get("Cash in CAD Combined")) or 0.0
                cash_usd = safe_float(r.get("Cash in USD")) or 0.0
                hh_total_mv += cash_cad + (cash_usd * fx)

    consolidated_tbl, _ = consolidated_positions_table(
        combined_pos_consolidated, fx, sector_data, subsector_data,
        combined_bal, hh_total_mv, currency_overrides)

    return (
        shared_html
        + "<h3>All Account Balances</h3>"
        + _combined_balance_table(chandu_data, nandu_data, currency_overrides)
        + "<h3>Consolidated Holdings</h3>"
        + consolidated_tbl
        + "<h3>Sector Allocation</h3>"
        + _household_sector_bars(chandu_data, nandu_data, sector_data, subsector_data, currency_overrides)
    )


# ---------------------------------------------------------------------------
# Error banner
# ---------------------------------------------------------------------------

def error_banner(errors: list) -> str:
    if not errors:
        return ""

    is_auth = any(
        "authentication" in m.lower() or "internal server error" in m.lower() or "token" in m.lower()
        for _, m in errors
    )
    rows = "".join(f"<li><strong>{person}:</strong> {msg}</li>" for person, msg in errors)

    if is_auth:
        steps = """
        <li>Open <strong>Questrade</strong> in your browser and log in (this refreshes the API token)</li>
        <li>Wait 30–60 seconds, then re-run: <code>python3 generate_report.py</code></li>
        <li>If it persists, open <code>ChanduAPITracker</code>, copy the refresh token, and paste it back to reset</li>
        """
    else:
        steps = """
        <li>Check your internet connection</li>
        <li>Re-run: <code>python3 generate_report.py</code></li>
        <li>If Nandu's data is missing, add Nandu's Questrade refresh token to <code>NanduAPITracker</code></li>
        """

    return f"""
<div style="background:#fff3cd;border-left:5px solid #f0a500;padding:16px 20px;margin:16px 28px;border-radius:6px;font-size:13px">
  <div style="font-size:15px;font-weight:700;color:#856404;margin-bottom:8px">&#9888; Questrade API — Data Fetch Issue</div>
  <ul style="margin:0 0 12px 18px;color:#533f03">
    {rows}
  </ul>
  <div style="font-weight:600;color:#533f03;margin-bottom:6px">Next steps:</div>
  <ol style="margin:0 0 0 18px;color:#533f03;line-height:1.7">
    {steps}
  </ol>
</div>"""


# ---------------------------------------------------------------------------
# CSS / JS
# ---------------------------------------------------------------------------

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       font-size: 13px; background: #f5f6fa; color: #222; }

header { background: #1a2744; color: #fff; padding: 16px 28px;
         display: flex; justify-content: space-between; align-items: center; }
header h1 { font-size: 20px; font-weight: 600; }
header p  { font-size: 12px; color: #aab; margin-top: 4px; }
.ccy-btn  { background: #4e9af1; color: #fff; border: none; border-radius: 6px;
            padding: 9px 20px; font-size: 13px; font-weight: 600; cursor: pointer;
            white-space: nowrap; }
.ccy-btn:hover { background: #3a86d6; }

.main-tab-bar { display: flex; background: #253159; padding: 0 20px; }
.maintab { background: none; border: none; color: #ccd; padding: 12px 22px;
           font-size: 13px; cursor: pointer; border-bottom: 3px solid transparent; }
.maintab.active { color: #fff; border-bottom-color: #4e9af1; }

.mainpanel { display: none; padding: 22px 28px; }
.mainpanel.active { display: block; }

.subtab-bar { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 16px; }
.subtab { background: #e8ecf5; border: none; border-radius: 4px; padding: 7px 14px;
          font-size: 12px; cursor: pointer; color: #444; }
.subtab.active { background: #1a2744; color: #fff; }
.subpanel { display: none; }
.subpanel.active { display: block; }

/* Tables */
table { width: 100%; border-collapse: collapse; background: #fff;
        border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.08);
        margin-top: 8px; }
.pos-tbl { table-layout: auto; }
.bal-tbl { table-layout: auto; }
th { background: #1a2744; color: #fff; text-align: left; padding: 8px 10px;
     font-size: 12px; font-weight: 500; }
td { padding: 7px 10px; border-bottom: 1px solid #eef; vertical-align: top;
     word-break: break-word; }
td.num, th.num { white-space: nowrap; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f0f4ff; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
tfoot tr td { background: #eef2ff; border-top: 2px solid #1a2744; font-weight: 600; }
tfoot tr:hover td { background: #eef2ff; }

/* P&L colours */
.pos { color: #1a7a3f; }
.neg { color: #c0392b; }
.card-value.pos { color: #1a7a3f; }
.card-value.neg { color: #c0392b; }

/* Household P&L card */
.summary-card.pos { background: #d4edda; }
.summary-card.pos .card-label { color: #155724; }
.summary-card.pos .card-value { color: #155724; }
.summary-card.neg { background: #f8d7da; }
.summary-card.neg .card-label { color: #721c24; }
.summary-card.neg .card-value { color: #721c24; }

/* Summary cards */
h3 { font-size: 14px; color: #1a2744; margin-bottom: 8px; margin-top: 20px; }
.summary-grid { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 8px; }
.summary-card { background: #fff; border-radius: 8px; padding: 16px 20px;
                box-shadow: 0 1px 4px rgba(0,0,0,.1); min-width: 170px; }
.summary-card.highlight { background: #1a2744; }
.summary-card.highlight .card-label { color: #aab; }
.summary-card.highlight .card-value { color: #fff; }
.card-label { font-size: 11px; text-transform: uppercase; letter-spacing: .5px;
              color: #888; margin-bottom: 6px; }
.card-value { font-size: 22px; font-weight: 700; color: #1a2744; }

/* Allocation bars */
.alloc-bars { background: #fff; border-radius: 6px; padding: 14px 18px;
              box-shadow: 0 1px 3px rgba(0,0,0,.08); max-width: 520px; margin-top: 8px; }
.bar-row   { display: flex; align-items: center; margin-bottom: 10px; }
.bar-label { width: 70px; font-size: 12px; color: #555; }
.bar-label-wide { width: 190px; font-size: 12px; color: #555; flex-shrink: 0; }
.bar-track { flex: 1; background: #eef; border-radius: 4px; height: 14px; margin: 0 10px; }
.bar-fill  { height: 14px; border-radius: 4px; }
.bar-pct   { width: 44px; text-align: right; font-size: 12px; }
.unknown-tickers { font-size: 10px; color: #999; }

details summary { cursor: pointer; padding: 8px 0; color: #1a2744; font-size: 13px; }
.alloc-warn { color: #c0392b; font-weight: 700; background: #fff3cd; padding: 1px 4px; border-radius: 2px; }

th.num { text-align: right; }

/* ETF row highlight */
.pos-tbl tbody tr.etf-row { background: #e8e8f8; }
.pos-tbl tbody tr.etf-row:hover { background: #d9d9f0; }

/* Asset class summary */
.asset-summary { background: #fff; border-radius: 8px; padding: 12px 16px;
                 box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 12px;
                 font-size: 12px; color: #666; }
.asset-summary strong { color: #1a2744; }

/* Legend note */
.legend-note { background: #f0f4ff; border-left: 4px solid #4e9af1; padding: 10px 14px;
               border-radius: 4px; margin-top: 12px; margin-bottom: 16px;
               font-size: 12px; color: #555; line-height: 1.4; }

/* Cash highlight */
.summary-card.cash-card { border: 2px solid #f28e2b; }
.summary-card.cash-card .card-value { color: #f28e2b; }

/* Compact balance table */
.bal-tbl[style*="width:auto"] td, .bal-tbl[style*="width:auto"] th { padding: 5px 10px; }

/* Subsector bars */
.subsector-bars { margin-top: 16px; max-width: 520px; }
.subsector-row { margin-bottom: 8px; }
.bar-label-subsector { width: 190px; font-size: 11px; color: #666; flex-shrink: 0;
                       padding-left: 16px; }
"""

JS = """
function showMainTab(btn, id) {
  document.querySelectorAll('.maintab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.mainpanel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(id).classList.add('active');
}
function showSubtab(btn, id) {
  const bar = btn.closest('.subtab-bar');
  const panel = bar.parentElement;
  bar.querySelectorAll('.subtab').forEach(b => b.classList.remove('active'));
  panel.querySelectorAll(':scope > .subpanel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(id).classList.add('active');
}

let activeView = 'combined-cad';
function switchView(view) {
  activeView = view;
  const views = ['combined-cad', 'combined-usd', 'cad', 'usd'];
  views.forEach(v => {
    document.querySelectorAll('.view-' + v).forEach(el => {
      el.style.display = (v === view) ? '' : 'none';
    });
  });
  document.querySelectorAll('.ccy-btn[data-view]').forEach(btn => {
    const active = btn.dataset.view === view;
    btn.style.fontWeight = active ? 'bold' : 'normal';
    btn.style.border = active ? '2px solid green' : '1px solid #ccc';
    btn.style.backgroundColor = active ? 'rgba(0,128,0,0.1)' : 'white';
  });
}
"""


# ---------------------------------------------------------------------------
# HTML assembler
# ---------------------------------------------------------------------------

def build_html(chandu_data: dict, nandu_data: dict, report_date: str, fx: float,
               sector_data: dict, subsector_data: dict,
               currency_overrides: dict = None, errors: list = None) -> str:
    if currency_overrides is None:
        currency_overrides = {}
    if errors is None:
        errors = []
    ch_tabs, ch_totals = person_tabs("Chandu", chandu_data, "ch", sector_data, subsector_data, currency_overrides)
    nd_tabs, nd_totals = person_tabs("Nandu",  nandu_data,  "nd", sector_data, subsector_data, currency_overrides)
    hh     = household_tab(chandu_data, nandu_data, ch_totals, nd_totals, sector_data, subsector_data, currency_overrides)
    banner = error_banner(errors)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Portfolio Report — {report_date}</title>
  <style>{CSS}</style>
</head>
<body>
<header>
  <div>
    <h1>Portfolio Report</h1>
    <p>As of {report_date}</p>
  </div>
</header>
{banner}
<div class="main-tab-bar">
  <button class="maintab active" onclick="showMainTab(this,'tab_household')">Household</button>
  <button class="maintab" onclick="showMainTab(this,'tab_chandu')">Chandu</button>
  <button class="maintab" onclick="showMainTab(this,'tab_nandu')">Nandu</button>
</div>
<div id="tab_household" class="mainpanel active">{hh}</div>
<div id="tab_chandu"    class="mainpanel">{ch_tabs}</div>
<div id="tab_nandu"     class="mainpanel">{nd_tabs}</div>
<script>{JS}</script>
</body>
</html>"""
