"""Trade signals engine: evaluate all automatable rules per holding."""

import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from .config import ACCOUNT_LABELS, YF_TICKER_MAP
from .utils import safe_float

# Status constants
PASS  = "PASS"
FAIL  = "FAIL"
WARN  = "WARN"
NA    = "N/A"

URGENCY_RANK = {"IMMEDIATE": 0, "THIS WEEK": 1, "MONITOR": 2, "NONE": 3}


# ---------------------------------------------------------------------------
# Technical data fetch
# ---------------------------------------------------------------------------

def fetch_technicals(symbols: list, spy_data: pd.DataFrame = None) -> dict:
    """Fetch all needed technical data for each symbol from yfinance.

    Returns {symbol: tech_dict}.
    """
    # Fetch SPY for RS rating baseline if not provided
    if spy_data is None:
        try:
            spy_raw = yf.download("SPY", period="1y", progress=False, auto_adjust=True)
            spy_data = spy_raw["Close"] if not spy_raw.empty else None
        except Exception:
            spy_data = None

    results = {}
    for sym in symbols:
        yf_sym = YF_TICKER_MAP.get(sym, sym)
        try:
            raw  = yf.download(yf_sym, period="1y", progress=False, auto_adjust=True)
            if raw.empty or len(raw) < 10:
                results[sym] = {"error": "insufficient data"}
                continue

            close  = raw["Close"].squeeze()
            high   = raw["High"].squeeze()
            low    = raw["Low"].squeeze()
            volume = raw["Volume"].squeeze()

            price      = float(close.iloc[-1])
            sma50      = float(close.tail(50).mean())  if len(close) >= 50  else None
            sma200     = float(close.tail(200).mean()) if len(close) >= 200 else None
            vol_avg50  = float(volume.tail(50).mean()) if len(volume) >= 50 else float(volume.mean())
            vol_today  = float(volume.iloc[-1])
            vol_ratio  = vol_today / vol_avg50 if vol_avg50 else None
            high_52w   = float(high.tail(252).max())
            recent_peak = float(close.tail(252).max())
            pct_from_peak = ((price - recent_peak) / recent_peak * 100) if recent_peak else 0

            pct_above_200 = ((price - sma200) / sma200 * 100) if sma200 else None

            # Trend
            if sma50 and sma200:
                if price > sma50 > sma200:
                    trend = "Stage 2 Uptrend"
                elif price > sma200:
                    trend = "Mixed"
                else:
                    trend = "Stage 4 Decline"
            elif sma200:
                trend = "Above 200-SMA" if price > sma200 else "Below 200-SMA"
            else:
                trend = "Insufficient data"

            golden_cross = (sma50 > sma200) if (sma50 and sma200) else None
            death_cross  = (sma50 < sma200) if (sma50 and sma200) else None

            # Consecutive down days (last 10)
            recent_closes = close.tail(11)
            changes = recent_closes.diff().dropna()
            consec_down = 0
            for ch in reversed(changes.values):
                if ch < 0:
                    consec_down += 1
                else:
                    break

            consec_up = 0
            for ch in reversed(changes.values):
                if ch > 0:
                    consec_up += 1
                else:
                    break

            # Closing near day low (last 5 days): close within X% of low
            closes_near_low = 0
            for i in range(min(5, len(raw))):
                c = float(close.iloc[-(i+1)])
                l = float(low.iloc[-(i+1)])
                h = float(high.iloc[-(i+1)])
                day_range = h - l
                if day_range > 0 and (c - l) / day_range < 0.25:
                    closes_near_low += 1

            # Distribution days last 25 sessions: down ≥0.2% on higher volume than prev day
            dist_days = 0
            recent = raw.tail(26)
            for i in range(1, min(25, len(recent))):
                c_today = float(recent["Close"].iloc[i])
                c_prev  = float(recent["Close"].iloc[i-1])
                v_today = float(recent["Volume"].iloc[i])
                v_prev  = float(recent["Volume"].iloc[i-1])
                pct_chg = (c_today - c_prev) / c_prev * 100
                if pct_chg <= -0.2 and v_today > v_prev:
                    dist_days += 1

            # RS Rating vs SPY (1-year return percentile placeholder)
            rs_pct = None
            if spy_data is not None and len(spy_data) >= 252:
                try:
                    spy_1y = float(spy_data.iloc[-252])
                    spy_now = float(spy_data.iloc[-1])
                    spy_return = (spy_now - spy_1y) / spy_1y * 100

                    stk_1y  = float(close.iloc[-min(252, len(close))])
                    stk_ret = (price - stk_1y) / stk_1y * 100
                    # Raw ratio — will be ranked across all symbols by caller
                    rs_pct = stk_ret - spy_return
                except Exception:
                    pass

            results[sym] = {
                "price":           price,
                "sma50":           sma50,
                "sma200":          sma200,
                "vol_today":       vol_today,
                "vol_avg50":       vol_avg50,
                "vol_ratio":       vol_ratio,
                "high_52w":        high_52w,
                "recent_peak":     recent_peak,
                "pct_from_peak":   pct_from_peak,
                "pct_above_200":   pct_above_200,
                "trend":           trend,
                "golden_cross":    golden_cross,
                "death_cross":     death_cross,
                "consec_down":     consec_down,
                "consec_up":       consec_up,
                "closes_near_low": closes_near_low,
                "dist_days":       dist_days,
                "rs_raw":          rs_pct,
                "error":           None,
            }
        except Exception as e:
            results[sym] = {"error": str(e)}
        time.sleep(0.25)

    # Rank RS across all fetched symbols (1–99 scale)
    rs_values = {s: d["rs_raw"] for s, d in results.items()
                 if not d.get("error") and d.get("rs_raw") is not None}
    if rs_values:
        sorted_syms = sorted(rs_values, key=lambda s: rs_values[s])
        n = len(sorted_syms)
        for rank, sym in enumerate(sorted_syms):
            results[sym]["rs_rating"] = int((rank / n) * 99) + 1
    for sym in results:
        if "rs_rating" not in results[sym]:
            results[sym]["rs_rating"] = None

    return results


# ---------------------------------------------------------------------------
# Rule evaluation — one function per rule, returns a result dict
# ---------------------------------------------------------------------------

def _result(rule, status, value, action=None, urgency="NONE", detail=""):
    return {
        "rule_id":  rule["rule_id"],
        "name":     rule["name"],
        "category": rule["category"],
        "status":   status,
        "value":    value,
        "action":   action,
        "urgency":  urgency,
        "detail":   detail,
    }


def _eval_position_limit(rule, pos, balances):
    p = rule["params"]
    max_pct = p.get("max_pct", 10)
    acct_num = str(int(pos["Account Number"])) if pd.notna(pos.get("Account Number")) else ""
    mv   = safe_float(pos.get("Market Value")) or 0.0
    # Find equity for this account
    eq = 0.0
    for _, b in balances.iterrows():
        if str(b.get("Account Number", "")).strip() == acct_num:
            eq = safe_float(b.get("Total Equity in CAD Combined")) or 0.0
            break
    if eq <= 0:
        return _result(rule, NA, "No balance data")
    weight = (mv / eq) * 100
    if weight > max_pct:
        trim_amt = round((weight - max_pct) / 100 * eq, 2)
        return _result(rule, FAIL, f"{weight:.1f}% of account",
                       action=f"Trim ${trim_amt:,.0f}", urgency="THIS WEEK",
                       detail=f"Max allowed: {max_pct}%. Reduce by ${trim_amt:,.0f}.")
    return _result(rule, PASS, f"{weight:.1f}% of account")


def _eval_sell_hard_stop(rule, pos, tech):
    p = rule["params"]
    trigger = p.get("trigger_pct", -7)
    cost  = safe_float(pos.get("Cost Per Share")) or 0.0
    price = tech.get("price") or safe_float(pos.get("Market Price")) or 0.0
    if cost <= 0 or price <= 0:
        return _result(rule, NA, "No cost data")
    gain = (price - cost) / cost * 100
    if gain <= trigger:
        return _result(rule, FAIL, f"{gain:+.1f}% from cost",
                       action="SELL IMMEDIATELY", urgency="IMMEDIATE",
                       detail=f"Down {abs(gain):.1f}% — hard stop at {trigger}%. No exceptions.")
    return _result(rule, PASS, f"{gain:+.1f}% from cost")


def _eval_sell_alt_stop(rule, pos, tech):
    p = rule["params"]
    t1 = p.get("first_trigger_pct", -5)
    t2 = p.get("second_trigger_pct", -10)
    pct1 = p.get("first_sell_pct", 50)
    cost  = safe_float(pos.get("Cost Per Share")) or 0.0
    price = tech.get("price") or safe_float(pos.get("Market Price")) or 0.0
    if cost <= 0 or price <= 0:
        return _result(rule, NA, "No cost data")
    gain = (price - cost) / cost * 100
    if gain <= t2:
        return _result(rule, FAIL, f"{gain:+.1f}%", action="SELL REST", urgency="IMMEDIATE",
                       detail=f"Past {t2}% — sell remaining position.")
    if gain <= t1:
        return _result(rule, WARN, f"{gain:+.1f}%", action=f"SELL {pct1}%", urgency="THIS WEEK",
                       detail=f"At {t1}% trigger — sell {pct1}% of position.")
    return _result(rule, PASS, f"{gain:+.1f}%")


def _eval_take_profits(rule, pos, tech):
    p = rule["params"]
    mn   = p.get("min_pct", 20)
    mx   = p.get("max_pct", 25)
    frac = p.get("sell_fraction", 0.33)
    cost  = safe_float(pos.get("Cost Per Share")) or 0.0
    qty   = safe_float(pos.get("Quantity")) or 0.0
    price = tech.get("price") or safe_float(pos.get("Market Price")) or 0.0
    if cost <= 0 or price <= 0:
        return _result(rule, NA, "No cost data")
    gain = (price - cost) / cost * 100
    if mn <= gain <= mx:
        sell_qty = round(qty * frac)
        sell_amt = round(sell_qty * price, 2)
        return _result(rule, WARN, f"{gain:+.1f}% gain",
                       action=f"Sell {int(frac*100)}% (${sell_amt:,.0f})", urgency="THIS WEEK",
                       detail=f"In profit-taking zone ({mn}–{mx}%). Sell {int(frac*100)}%.")
    if gain > mx:
        return _result(rule, WARN, f"{gain:+.1f}% gain",
                       action="Monitor / Extended", urgency="MONITOR",
                       detail=f"Above take-profit zone. Watch for climax/distribution signals.")
    return _result(rule, PASS, f"{gain:+.1f}% gain")


def _eval_climax_run(rule, pos, tech):
    trigger = rule["params"].get("trigger_pct", 70)
    cost  = safe_float(pos.get("Cost Per Share")) or 0.0
    price = tech.get("price") or safe_float(pos.get("Market Price")) or 0.0
    if cost <= 0 or price <= 0:
        return _result(rule, NA, "No cost data")
    gain = (price - cost) / cost * 100
    if gain >= trigger:
        return _result(rule, WARN, f"{gain:+.1f}% from cost",
                       action="Consider Full Exit", urgency="THIS WEEK",
                       detail=f"Up {gain:.0f}% — likely climax run. Consider full exit.")
    return _result(rule, PASS, f"{gain:+.1f}% from cost")


def _eval_above_200_extended(rule, pos, tech):
    trigger = rule["params"].get("trigger_pct", 70)
    pct = tech.get("pct_above_200")
    if pct is None:
        return _result(rule, NA, "No 200-SMA data")
    if pct >= trigger:
        return _result(rule, WARN, f"{pct:+.1f}% above 200-SMA",
                       action="Consider Selling", urgency="THIS WEEK",
                       detail=f"Extended {pct:.0f}% above 200-SMA — historically a sell zone.")
    return _result(rule, PASS, f"{pct:+.1f}% above 200-SMA" if pct >= 0 else f"{pct:.1f}% below 200-SMA")


def _eval_peak_decline(rule, pos, tech):
    trigger = rule["params"].get("trigger_pct", -12)
    pct = tech.get("pct_from_peak")
    if pct is None:
        return _result(rule, NA, "No peak data")
    if pct <= trigger:
        return _result(rule, WARN, f"{pct:.1f}% from 52W peak",
                       action="Review Position", urgency="MONITOR",
                       detail=f"Down {abs(pct):.0f}% from recent peak — watch for continued weakness.")
    return _result(rule, PASS, f"{pct:.1f}% from 52W peak")


def _eval_sma50_break(rule, pos, tech):
    vol_thresh = rule["params"].get("volume_threshold", 1.3)
    price  = tech.get("price")
    sma50  = tech.get("sma50")
    vol_r  = tech.get("vol_ratio")
    if price is None or sma50 is None:
        return _result(rule, NA, "No SMA data")
    if price < sma50:
        vol_str  = f" on {vol_r:.1f}x volume" if vol_r else ""
        urgency  = "THIS WEEK" if (vol_r and vol_r >= vol_thresh) else "MONITOR"
        return _result(rule, FAIL, f"${price:.2f} < ${sma50:.2f} 50-SMA",
                       action="Watch / Sell", urgency=urgency,
                       detail=f"Below 50-SMA{vol_str}. {'Heavy volume = distribution.' if vol_r and vol_r >= vol_thresh else 'Monitor for follow-through.'}")
    pct_above = (price - sma50) / sma50 * 100
    return _result(rule, PASS, f"{pct_above:+.1f}% above 50-SMA")


def _eval_below_200(rule, pos, tech):
    price  = tech.get("price")
    sma200 = tech.get("sma200")
    if price is None or sma200 is None:
        return _result(rule, NA, "No 200-SMA data")
    if price < sma200:
        return _result(rule, FAIL, f"${price:.2f} < ${sma200:.2f} 200-SMA",
                       action="SELL", urgency="THIS WEEK",
                       detail="Below 200-SMA. Per personal rule: this is the hard sell line.")
    pct = (price - sma200) / sma200 * 100
    return _result(rule, PASS, f"{pct:+.1f}% above 200-SMA")


def _eval_exhaustion_sharan(rule, pos, tech):
    vol_thresh = rule["params"].get("volume_threshold", 1.0)
    price = tech.get("price")
    sma50 = tech.get("sma50")
    vol_r = tech.get("vol_ratio")
    if price is None or sma50 is None:
        return _result(rule, NA, "No SMA data")
    below_50   = price < sma50
    heavy_vol  = (vol_r and vol_r >= vol_thresh)
    if below_50 and heavy_vol:
        return _result(rule, FAIL, f"Below 50-SMA on {vol_r:.1f}x vol",
                       action="SELL", urgency="IMMEDIATE",
                       detail="Sharan's rule: exhaustion gap + below 50-SMA + distribution volume. Sell.")
    if below_50:
        return _result(rule, WARN, f"Below 50-SMA (vol: {vol_r:.1f}x)" if vol_r else "Below 50-SMA",
                       action="Monitor", urgency="MONITOR")
    return _result(rule, PASS, "Above 50-SMA, no exhaustion signal")


def _eval_poor_rs(rule, tech):
    min_rs = rule["params"].get("min_rs", 70)
    rs = tech.get("rs_rating")
    if rs is None:
        return _result(rule, NA, "RS not calculated")
    if rs < min_rs:
        return _result(rule, WARN, f"RS {rs}",
                       action="Review", urgency="MONITOR",
                       detail=f"RS {rs} below minimum {min_rs}. Laggard — consider replacing.")
    return _result(rule, PASS, f"RS {rs}")


def _eval_canslim_l(rule, tech):
    min_rs = rule["params"].get("min_rs", 80)
    rs = tech.get("rs_rating")
    if rs is None:
        return _result(rule, NA, "RS not calculated")
    if rs < min_rs:
        return _result(rule, FAIL, f"RS {rs} < {min_rs}", urgency="MONITOR",
                       detail=f"Not a market leader. RS {rs} below threshold of {min_rs}.")
    return _result(rule, PASS, f"RS {rs} ✓")


def _eval_consecutive_down(rule, tech):
    lookback  = rule["params"].get("lookback_days", 10)
    threshold = rule["params"].get("threshold", 3)
    down = tech.get("consec_down", 0)
    up   = tech.get("consec_up", 0)
    if down >= threshold and down > up:
        return _result(rule, WARN, f"{down} consecutive down days",
                       action="Monitor", urgency="MONITOR",
                       detail=f"{down} down days in a row — watch for distribution pattern.")
    return _result(rule, PASS, f"{down} down / {up} up days")


def _eval_closing_low(rule, tech):
    lookback  = rule["params"].get("lookback_days", 5)
    threshold = rule["params"].get("threshold_pct", 0.05)
    closes_near = tech.get("closes_near_low", 0)
    if closes_near >= 3:
        return _result(rule, WARN, f"{closes_near}/{lookback} days closing near low",
                       action="Monitor", urgency="MONITOR",
                       detail="Repeated closes near day low — institutional selling pattern.")
    return _result(rule, PASS, f"{closes_near}/{lookback} days near low")


def _eval_new_high_low_vol(rule, tech):
    vol_thresh = rule["params"].get("volume_threshold", 0.8)
    price    = tech.get("price")
    high_52w = tech.get("high_52w")
    vol_r    = tech.get("vol_ratio")
    if price is None or high_52w is None:
        return _result(rule, NA, "No price data")
    near_high = price >= high_52w * 0.98
    low_vol   = vol_r is not None and vol_r < vol_thresh
    if near_high and low_vol:
        return _result(rule, WARN, f"Near 52W high on {vol_r:.1f}x vol",
                       action="Caution", urgency="MONITOR",
                       detail="Near new high but volume is weak — unconfirmed breakout.")
    return _result(rule, PASS, f"Vol {vol_r:.1f}x avg" if vol_r else "N/A")


def _eval_distribution_volume(rule, tech):
    dist = tech.get("dist_days", 0)
    if dist >= 4:
        return _result(rule, WARN, f"{dist} distribution days (25 sessions)",
                       action="Reduce Risk", urgency="THIS WEEK",
                       detail=f"{dist} distribution days in recent 25 sessions — institutional selling.")
    if dist >= 2:
        return _result(rule, WARN, f"{dist} distribution days",
                       action="Monitor", urgency="MONITOR")
    return _result(rule, PASS, f"{dist} distribution days")


def _eval_golden_cross(rule, tech):
    gc = tech.get("golden_cross")
    sma50  = tech.get("sma50")
    sma200 = tech.get("sma200")
    if gc is None:
        return _result(rule, NA, "No SMA data")
    if gc:
        return _result(rule, PASS, f"50-SMA ${sma50:.2f} > 200-SMA ${sma200:.2f}")
    return _result(rule, WARN, f"50-SMA ${sma50:.2f} < 200-SMA ${sma200:.2f}",
                   action="Monitor", urgency="MONITOR",
                   detail="Death cross active. Wait for 50-SMA reclaim with volume.")


def _eval_death_cross(rule, tech):
    dc     = tech.get("death_cross")
    sma50  = tech.get("sma50")
    sma200 = tech.get("sma200")
    if dc is None:
        return _result(rule, NA, "No SMA data")
    if dc:
        return _result(rule, WARN, f"Death cross: 50-SMA ${sma50:.2f} < 200-SMA ${sma200:.2f}",
                       action="Caution", urgency="MONITOR",
                       detail="Death cross. Wait for 50-SMA to reclaim 200-SMA with heavy volume.")
    return _result(rule, PASS, "No death cross")


def _eval_failed_breakout(rule, pos, tech):
    trigger = rule["params"].get("trigger_pct", -3)
    cost  = safe_float(pos.get("Cost Per Share")) or 0.0
    price = tech.get("price") or safe_float(pos.get("Market Price")) or 0.0
    if cost <= 0 or price <= 0:
        return _result(rule, NA, "No cost data")
    gain = (price - cost) / cost * 100
    if trigger <= gain < 0:
        return _result(rule, WARN, f"{gain:+.1f}% — near cost basis",
                       action="Sell if confirms", urgency="THIS WEEK",
                       detail="Dropped back toward buy point — possible failed breakout.")
    if gain < trigger:
        return _result(rule, FAIL, f"{gain:+.1f}% below cost",
                       action="SELL", urgency="THIS WEEK",
                       detail="Failed breakout confirmed — below buy point.")
    return _result(rule, PASS, f"{gain:+.1f}% above cost")


# Map rule_id → evaluator
_EVALUATORS = {
    "position_limit":        lambda rule, pos, tech, bal: _eval_position_limit(rule, pos, bal),
    "sell_hard_stop":        lambda rule, pos, tech, bal: _eval_sell_hard_stop(rule, pos, tech),
    "sell_alt_stop":         lambda rule, pos, tech, bal: _eval_sell_alt_stop(rule, pos, tech),
    "sell_take_profits":     lambda rule, pos, tech, bal: _eval_take_profits(rule, pos, tech),
    "sell_climax_run":       lambda rule, pos, tech, bal: _eval_climax_run(rule, pos, tech),
    "sell_above_200_extended": lambda rule, pos, tech, bal: _eval_above_200_extended(rule, pos, tech),
    "sell_peak_decline":     lambda rule, pos, tech, bal: _eval_peak_decline(rule, pos, tech),
    "sell_sma50_break":      lambda rule, pos, tech, bal: _eval_sma50_break(rule, pos, tech),
    "sell_below_200":        lambda rule, pos, tech, bal: _eval_below_200(rule, pos, tech),
    "sell_exhaustion_sharan":lambda rule, pos, tech, bal: _eval_exhaustion_sharan(rule, pos, tech),
    "sell_poor_rs":          lambda rule, pos, tech, bal: _eval_poor_rs(rule, tech),
    "sell_consecutive_down": lambda rule, pos, tech, bal: _eval_consecutive_down(rule, tech),
    "sell_closing_low":      lambda rule, pos, tech, bal: _eval_closing_low(rule, tech),
    "sell_new_high_low_vol": lambda rule, pos, tech, bal: _eval_new_high_low_vol(rule, tech),
    "sell_distribution_volume": lambda rule, pos, tech, bal: _eval_distribution_volume(rule, tech),
    "sell_failed_breakout":  lambda rule, pos, tech, bal: _eval_failed_breakout(rule, pos, tech),
    "canslim_l":             lambda rule, pos, tech, bal: _eval_canslim_l(rule, tech),
    "market_golden_cross":   lambda rule, pos, tech, bal: _eval_golden_cross(rule, tech),
    "market_death_cross":    lambda rule, pos, tech, bal: _eval_death_cross(rule, tech),
    "market_distribution_day": lambda rule, pos, tech, bal: _eval_distribution_volume(rule, tech),
}


# ---------------------------------------------------------------------------
# Evaluate all enabled automatable rules for one position
# ---------------------------------------------------------------------------

def evaluate_position(pos: pd.Series, tech: dict, balances: pd.DataFrame,
                      rules: list) -> list:
    """Return list of rule result dicts for a single position."""
    results = []
    for rule in rules:
        if not rule.get("enabled") or not rule.get("automatable"):
            continue
        rid = rule["rule_id"]
        evaluator = _EVALUATORS.get(rid)
        if evaluator is None:
            continue
        try:
            res = evaluator(rule, pos, tech, balances)
            results.append(res)
        except Exception as e:
            results.append(_result(rule, NA, f"Error: {e}"))
    return results


# ---------------------------------------------------------------------------
# Build holdings table
# ---------------------------------------------------------------------------

def build_holdings_table(chandu_data: dict, nandu_data: dict,
                         technicals: dict, rules: list) -> list:
    """Build one row per holding with all rule evaluations."""
    rows = []

    frames, bal_frames = [], []
    for data in [chandu_data, nandu_data]:
        pos = data.get("Positions", pd.DataFrame())
        bal = data.get("Balances",  pd.DataFrame())
        if not pos.empty:
            frames.append(pos)
        if not bal.empty:
            bal_frames.append(bal)

    all_positions = pd.concat(frames,     ignore_index=True) if frames     else pd.DataFrame()
    all_balances  = pd.concat(bal_frames, ignore_index=True) if bal_frames else pd.DataFrame()

    if all_positions.empty:
        return rows

    non_opt = all_positions
    if "Asset Class" in all_positions.columns:
        non_opt = all_positions[all_positions["Asset Class"].str.upper() != "OPT"]

    for _, pos in non_opt.iterrows():
        sym      = str(pos.get("Equity Symbol", "")).strip()
        acct_num = str(int(pos["Account Number"])) if pd.notna(pos.get("Account Number")) else ""
        person   = str(pos.get("_person", ""))
        account  = f"{person} — {ACCOUNT_LABELS.get(acct_num, acct_num)}"
        cost     = safe_float(pos.get("Cost Per Share")) or 0.0
        qty      = safe_float(pos.get("Quantity"))       or 0.0

        tech = technicals.get(sym, {})
        price    = tech.get("price") or safe_float(pos.get("Market Price")) or 0.0
        gain_pct = ((price - cost) / cost * 100) if cost > 0 and price > 0 else 0.0

        rule_results = evaluate_position(pos, tech, all_balances, rules)

        # Determine worst signal
        worst_urgency = "NONE"
        actions = [r["action"] for r in rule_results if r["action"] and r["status"] in (FAIL, WARN)]
        for r in rule_results:
            if URGENCY_RANK.get(r["urgency"], 99) < URGENCY_RANK.get(worst_urgency, 99):
                worst_urgency = r["urgency"]

        rows.append({
            "person":        person,
            "account":       account,
            "symbol":        sym,
            "description":   str(pos.get("Equity Description", sym)),
            "qty":           qty,
            "cost_basis":    round(cost, 2),
            "current_price": round(price, 2),
            "pl_pct":        round(gain_pct, 2),
            "trend":         tech.get("trend", "No data"),
            "sma50":         round(tech["sma50"],  2) if tech.get("sma50")  else None,
            "sma200":        round(tech["sma200"], 2) if tech.get("sma200") else None,
            "rs_rating":     tech.get("rs_rating"),
            "worst_urgency": worst_urgency,
            "actions":       actions,
            "rule_results":  rule_results,
            "data_error":    tech.get("error"),
        })

    return rows


# ---------------------------------------------------------------------------
# Action items summary
# ---------------------------------------------------------------------------

def build_action_items(holdings: list) -> list:
    """Flatten all rule failures/warnings into a prioritised action list."""
    items = []
    priority_map = {"IMMEDIATE": 1, "THIS WEEK": 2, "MONITOR": 3, "NONE": 4}

    for h in holdings:
        for r in h["rule_results"]:
            if r["status"] in (FAIL, WARN) and r.get("action"):
                items.append({
                    "priority":   priority_map.get(r["urgency"], 4),
                    "urgency":    r["urgency"],
                    "symbol":     h["symbol"],
                    "account":    h["account"],
                    "action":     r["action"],
                    "rule":       r["name"],
                    "value":      r["value"],
                    "detail":     r["detail"],
                    "pl_pct":     h["pl_pct"],
                })

    items.sort(key=lambda x: (x["priority"], x["symbol"]))
    return items


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_signals(chandu_data: dict, nandu_data: dict, rules: list) -> dict:
    """Run full signals engine. Returns holdings table + action items."""
    # Collect all non-option symbols
    symbols = set()
    for data in [chandu_data, nandu_data]:
        pos = data.get("Positions", pd.DataFrame())
        if not pos.empty and "Equity Symbol" in pos.columns:
            non_opt = pos[pos["Asset Class"].str.upper() != "OPT"] \
                if "Asset Class" in pos.columns else pos
            symbols.update(non_opt["Equity Symbol"].dropna().astype(str).tolist())

    technicals = fetch_technicals(sorted(symbols))
    holdings   = build_holdings_table(chandu_data, nandu_data, technicals, rules)
    actions    = build_action_items(holdings)

    return {
        "holdings":    holdings,
        "actions":     actions,
        "technicals":  technicals,
    }
