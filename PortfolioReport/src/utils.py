"""Pure utility functions: type coercion, numeric formatting, currency conversion, HTML cell builders."""

from typing import Optional
from .config import ACCOUNT_LABELS


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------

def safe_float(val) -> Optional[float]:
    try:
        v = float(val)
        import math
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Currency conversion
# ---------------------------------------------------------------------------

def conv_cad(val, ccy: str, fx: float) -> float:
    v = safe_float(val)
    if v is None:
        return 0.0
    return v * fx if str(ccy).upper() == "USD" else v


def conv_usd(val, ccy: str, fx: float) -> float:
    v = safe_float(val)
    if v is None:
        return 0.0
    return v / fx if str(ccy).upper() == "CAD" else v


def get_currency(symbol: str, questrade_ccy: str, overrides: dict) -> str:
    """Return correct currency for symbol, checking overrides first."""
    return overrides.get(symbol, questrade_ccy)


# ---------------------------------------------------------------------------
# Display formatting
# ---------------------------------------------------------------------------

def fmt_cad(val) -> str:
    v = safe_float(val)
    return f"${v:,.2f}" if v is not None else "—"


def fmt_usd(val) -> str:
    v = safe_float(val)
    return f"US${v:,.2f}" if v is not None else "—"


def fmt_pct(val) -> str:
    v = safe_float(val)
    return f"{v:.2f}%" if v is not None else "—"


def fmt_qty(val) -> str:
    v = safe_float(val)
    return f"{v:.1f}" if v is not None else "—"


def pnl_class(val) -> str:
    v = safe_float(val)
    if v is None:
        return ""
    return "pos" if v >= 0 else "neg"


def account_label(acct_num) -> str:
    s = str(int(acct_num)) if not isinstance(acct_num, str) else acct_num.strip()
    lbl = ACCOUNT_LABELS.get(s, "")
    return f"{lbl} ({s})" if lbl else s


# ---------------------------------------------------------------------------
# HTML table cell / header builders
# ---------------------------------------------------------------------------

def money_td(cad_val: float, usd_val: float, pnl: bool = False) -> str:
    """Two plain <td> cells (CAD + USD). Used in positions tables."""
    extra = pnl_class(cad_val) if pnl else ""
    cls = " ".join(c for c in ["num", "money", extra] if c)
    return f'<td class="{cls}">{fmt_cad(cad_val)}</td><td class="{cls}">{fmt_usd(usd_val)}</td>'


def money_td_native(val: float, currency: str, pnl: bool = False) -> str:
    """Single <td> in native currency. Used in positions tables."""
    extra = pnl_class(val) if pnl else ""
    cls = " ".join(c for c in ["num", "money", extra] if c)
    display = fmt_usd(val) if str(currency).upper() == "USD" else fmt_cad(val)
    return f'<td class="{cls}">{display}</td>'


def money_td_multiview(combined_cad: float, combined_usd: float, native_cad: float, native_usd: float, pnl: bool = False) -> str:
    """Four <td> cells for the 4-view currency toggle (balance tables)."""
    def _cls(val, view):
        extra = pnl_class(val) if pnl else ""
        return " ".join(c for c in ["num", "money", f"view-{view}", extra] if c)

    return (
        f'<td class="{_cls(combined_cad, "combined-cad")}">{fmt_cad(combined_cad)}</td>'
        f'<td class="{_cls(combined_usd, "combined-usd")}" style="display:none">{fmt_usd(combined_usd)}</td>'
        f'<td class="{_cls(native_cad, "cad")}" style="display:none">{fmt_cad(native_cad)}</td>'
        f'<td class="{_cls(native_usd, "usd")}" style="display:none">{fmt_usd(native_usd)}</td>'
    )


def money_th(cad_label: str, usd_label: str) -> str:
    """Four <th> cells matching money_td_multiview (balance tables)."""
    return (
        f'<th class="num money view-combined-cad">{cad_label}</th>'
        f'<th class="num money view-combined-usd" style="display:none">{usd_label}</th>'
        f'<th class="num money view-cad" style="display:none">{cad_label}</th>'
        f'<th class="num money view-usd" style="display:none">{usd_label}</th>'
    )


def money_th_native(label: str) -> str:
    """Single <th> for native currency (positions tables)."""
    return f'<th class="num money">{label}</th>'


def money_th_simple(cad_label: str, usd_label: str) -> str:
    """Two plain <th> matching money_td output (no view toggling)."""
    return f'<th class="num money">{cad_label}</th><th class="num money">{usd_label}</th>'
