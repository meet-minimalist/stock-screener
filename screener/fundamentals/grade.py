from __future__ import annotations

from dataclasses import dataclass

from screener.fundamentals.schema import Fundamentals

# Overall grade weights across the four core dimensions (dividend is shown but
# not scored, so non-payers aren't penalised). Tunable.
DIMENSION_WEIGHTS = {"value": 0.25, "quality": 0.30, "growth": 0.25, "health": 0.20}


@dataclass
class FundamentalGrade:
    value: float | None        # 0-100, cheaper = higher
    quality: float | None      # 0-100, more profitable = higher
    growth: float | None       # 0-100, faster = higher
    health: float | None       # 0-100, stronger balance sheet = higher
    dividend: float | None     # 0-100, higher yield = higher (informational)
    overall: float | None      # 0-100 weighted blend of the four core dims
    letter: str                # A / B / C / D / F (— if ungraded)


def _ramp(v: float | None, lo: float, hi: float) -> float | None:
    """0..1 as v goes lo->hi (clamped). None passes through."""
    if v is None:
        return None
    if hi == lo:
        return 1.0 if v >= hi else 0.0
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def _inv(v: float | None, lo: float, hi: float) -> float | None:
    """1..0 as v goes lo->hi — for 'lower is better' metrics."""
    r = _ramp(v, lo, hi)
    return None if r is None else 1.0 - r


def _avg(*scores: float | None) -> float | None:
    present = [s for s in scores if s is not None]
    return sum(present) / len(present) if present else None


def _value(f: Fundamentals) -> float | None:
    pe = 0.0 if (f.pe is not None and f.pe < 0) else _inv(f.pe, 10, 40)
    fpe = 0.0 if (f.forward_pe is not None and f.forward_pe < 0) else _inv(f.forward_pe, 10, 35)
    return _avg(pe, fpe, _inv(f.peg, 0.5, 3.0), _inv(f.ps, 1, 10),
                _inv(f.pb, 1, 8), _inv(f.pfcf, 10, 40))


def _quality(f: Fundamentals) -> float | None:
    # promoter_holding is an India governance signal (skin in the game); None for
    # US, so it simply doesn't contribute there.
    return _avg(_ramp(f.roe, 0, 25), _ramp(f.roa, 0, 12), _ramp(f.roi, 0, 20),
                _ramp(f.gross_margin, 0, 60), _ramp(f.oper_margin, 0, 25),
                _ramp(f.net_margin, 0, 20), _ramp(f.promoter_holding, 25, 55))


def _growth(f: Fundamentals) -> float | None:
    return _avg(_ramp(f.eps_growth, 0, 25), _ramp(f.eps_growth_next_y, 0, 25),
                _ramp(f.eps_growth_5y, 0, 20), _ramp(f.sales_growth, 0, 20))


def _health(f: Fundamentals) -> float | None:
    return _avg(_inv(f.debt_equity, 0.3, 2.5), _inv(f.lt_debt_equity, 0.2, 2.0),
                _ramp(f.current_ratio, 1.0, 2.5), _ramp(f.quick_ratio, 0.5, 1.5))


def _letter(overall: float | None) -> str:
    if overall is None:
        return "—"
    for cutoff, grade in ((80, "A"), (68, "B"), (56, "C"), (44, "D")):
        if overall >= cutoff:
            return grade
    return "F"


def grade(f: Fundamentals, weights: dict | None = None) -> FundamentalGrade:
    """Grade one stock across the five fundamental dimensions (each 0-100)."""
    weights = weights or DIMENSION_WEIGHTS
    dims = {
        "value": _value(f), "quality": _quality(f),
        "growth": _growth(f), "health": _health(f),
    }
    num = sum(weights[k] * dims[k] for k in weights if dims[k] is not None)
    den = sum(weights[k] for k in weights if dims[k] is not None)
    overall = round(num / den * 100, 1) if den > 0 else None
    dividend = _ramp(f.dividend_yield, 0, 4)

    return FundamentalGrade(
        value=round(dims["value"] * 100, 1) if dims["value"] is not None else None,
        quality=round(dims["quality"] * 100, 1) if dims["quality"] is not None else None,
        growth=round(dims["growth"] * 100, 1) if dims["growth"] is not None else None,
        health=round(dims["health"] * 100, 1) if dims["health"] is not None else None,
        dividend=round(dividend * 100, 1) if dividend is not None else None,
        overall=overall,
        letter=_letter(overall),
    )
