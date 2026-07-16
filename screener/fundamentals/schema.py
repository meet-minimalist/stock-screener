from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields

# Fields parsed as plain numbers vs percentages is a source concern; the schema
# just stores floats. Percentage fields hold the numeric percent (e.g. 15.3 for
# "15.3%"); ratio fields hold the ratio (e.g. 0.5 for Debt/Eq).
_STR_FIELDS = ("ticker", "as_of", "sector", "industry")


def to_float(value) -> float | None:
    """Parse a finviz/CSV cell to a float, or None for missing/blank/'-'."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", "")
    if s in ("", "-", "nan", "NaN", "None"):
        return None
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except ValueError:
        return None


def to_pct(value) -> float | None:
    """Normalise a percentage cell to a percent number (e.g. 21.33 for 21.33%).

    finvizfinance is inconsistent: some percent columns arrive as ``"13.90%"``
    strings, others as already-divided floats (``0.2133`` meaning 21.33%). Strings
    keep their printed magnitude; bare floats are treated as fractions and scaled
    up by 100 so every percentage field ends on the same scale.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        if s in ("", "-", "nan", "NaN", "None"):
            return None
        if s.endswith("%"):
            s = s[:-1]
            try:
                return float(s)
            except ValueError:
                return None
        try:
            return float(s)  # bare numeric string: already a percent number
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        return float(value) * 100.0  # fraction from finvizfinance -> percent
    return None


@dataclass
class Fundamentals:
    """Normalised fundamentals for one stock at a point in time.

    Percentage metrics (roe, roi, net_margin, eps_growth, sales_growth,
    dividend_yield) are stored as numeric percents; debt_equity/pe/peg/ps/pb are
    ratios; market_cap is absolute. Any unavailable metric is ``None`` so scoring
    can treat it as neutral rather than failing.
    """

    ticker: str
    as_of: str
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    # Valuation
    pe: float | None = None
    forward_pe: float | None = None
    peg: float | None = None
    ps: float | None = None
    pb: float | None = None
    pfcf: float | None = None
    # Profitability / quality (percentages)
    roe: float | None = None
    roa: float | None = None
    roi: float | None = None          # ROIC
    gross_margin: float | None = None
    oper_margin: float | None = None
    net_margin: float | None = None
    # Growth (percentages)
    eps_growth: float | None = None            # EPS this year
    eps_growth_next_y: float | None = None
    eps_growth_5y: float | None = None         # EPS next 5Y (est.)
    eps_growth_past5y: float | None = None
    sales_growth: float | None = None          # Sales past 5Y
    # Financial health
    debt_equity: float | None = None
    lt_debt_equity: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    # Income + ownership/sentiment (percentages)
    dividend_yield: float | None = None
    insider_own: float | None = None
    inst_own: float | None = None
    short_float: float | None = None

    def to_row(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> "Fundamentals":
        """Rebuild from a CSV/dict row, coercing numeric fields back to floats."""
        values: dict = {}
        for f in fields(cls):
            raw = row.get(f.name)
            if f.name in _STR_FIELDS:
                s = None if raw is None else str(raw).strip()
                values[f.name] = None if s in (None, "", "nan", "None") else s
            else:
                values[f.name] = to_float(raw)
        return cls(**values)
