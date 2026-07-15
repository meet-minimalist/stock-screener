from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from screener.screeners.sector_rotation import _return_pct
from screener.screeners.strategies import _find_cross_above

# How much a sector's RRG quadrant helps a stock in it.
QUADRANT_TAILWIND = {
    "Leading": 1.0,
    "Improving": 0.75,
    "Weakening": 0.40,
    "Lagging": 0.10,
    "n/a": 0.50,
}

# Composite weights (must sum to 1.0). Tunable — this is the knob for style.
DEFAULT_WEIGHTS = {
    "sector": 0.20,       # sector tailwind (RRG)
    "trend": 0.20,        # 3M/6M/12M trend + above moving averages
    "rel_strength": 0.15, # beating its own sector
    "volatility": 0.10,   # lively enough to trade
    "trigger": 0.15,      # a fresh catalyst today
    "fundamental": 0.20,  # value + quality + growth
}


@dataclass
class Gates:
    """Hard liquidity/quality filters — fail any and the stock is excluded."""
    min_price: float = 5.0
    min_dollar_vol: float = 5_000_000.0  # 20-day avg of close*volume
    # Fundamental gate (applied only when the metric is present).
    max_pe: float = 80.0            # drop richly-priced names
    drop_negative_pe: bool = True   # drop money-losers (P/E < 0)
    max_debt_equity: float = 3.0    # drop over-levered balance sheets


def _volatility_fit(vol: float) -> float:
    """Reward tradeable daily volatility; punish dead or chaotic names. 0..1.

    Rises from 0 (~0.5% daily) to 1 (~2.5%), plateaus through ~6%, then decays
    toward 0.2 by ~12% (too wild to hold).
    """
    if vol <= 0.5:
        return 0.0
    if vol <= 2.5:
        return (vol - 0.5) / 2.0
    if vol <= 6.0:
        return 1.0
    if vol <= 12.0:
        return max(0.2, 1.0 - (vol - 6.0) / 6.0 * 0.8)
    return 0.2


def _trend_score(
    r3: float | None, r6: float | None, r12: float | None,
    price: float, sma50: float | None, sma200: float | None,
) -> float:
    """Positive trailing returns + price above its moving averages. 0..1."""
    rets = [r for r in (r3, r6, r12) if r is not None]
    pos_frac = (sum(1 for r in rets if r > 0) / len(rets)) if rets else 0.0
    above50 = 1.0 if (sma50 is not None and price > sma50) else 0.0
    above200 = 1.0 if (sma200 is not None and price > sma200) else 0.0
    return 0.5 * pos_frac + 0.25 * above50 + 0.25 * above200


def _rel_strength_score(stock_r3: float | None, sector_r3: float | None) -> float:
    """Stock's 3M return vs its sector's 3M return, squashed to 0..1.

    Matching the sector -> 0.5; beating it by ~20pts -> 1.0; lagging by ~20 -> 0.
    """
    if stock_r3 is None or sector_r3 is None:
        return 0.5
    rel = stock_r3 - sector_r3
    return min(1.0, max(0.0, 0.5 + rel / 40.0))


def _triggers(df: pd.DataFrame) -> tuple[float, list[str]]:
    """Fresh catalysts firing on the latest bar. Returns (score 0..1, reasons)."""
    close = df["Close"]
    fired: list[str] = []
    score = 0.0

    lookback = min(252, len(close))
    high = close.rolling(lookback, min_periods=20).max().iloc[-1]
    if high > 0 and (high - close.iloc[-1]) / high <= 0.03:
        fired.append("near 52w high")
        score += 0.4

    if "Volume" in df.columns:
        vol = df["Volume"]
        avg = vol.rolling(20).mean().iloc[-1]
        if avg and avg > 0 and vol.iloc[-1] >= 2 * avg:
            fired.append(f"{vol.iloc[-1] / avg:.1f}x volume")
            score += 0.3

    macd_cols = [c for c in df.columns if c.startswith("MACD_")]
    sig_cols = [c for c in df.columns if c.startswith("MACDs")]
    if macd_cols and sig_cols and len(df) >= 6:
        cross = _find_cross_above(df, macd_cols[0], sig_cols[0])
        if cross is not None and len(cross) and cross[-1] >= df.index[-5]:
            fired.append("MACD cross")
            score += 0.3

    if len(close) >= 2:
        day = (close.iloc[-1] / close.iloc[-2] - 1.0) * 100.0
        if day >= 4.0:
            fired.append(f"+{day:.0f}% today")
            score += 0.2

    return min(1.0, score), fired


def _liquidity_ok(df: pd.DataFrame, gates: Gates) -> tuple[bool, str]:
    close = df["Close"]
    price = float(close.iloc[-1])
    if price < gates.min_price:
        return False, f"price ${price:.2f} < ${gates.min_price:.0f}"
    if "Volume" not in df.columns:
        return False, "no volume data"
    dvol = float((close * df["Volume"]).rolling(20).mean().iloc[-1])
    if dvol < gates.min_dollar_vol:
        return False, f"${dvol / 1e6:.1f}M avg $-vol"
    return True, ""


def _fundamental_gate(fund, gates: Gates) -> tuple[bool, str]:
    """Reject obviously weak fundamentals. Missing metrics never fail the gate."""
    if fund is None:
        return True, ""
    if fund.pe is not None:
        if gates.drop_negative_pe and fund.pe < 0:
            return False, "negative earnings"
        if fund.pe > gates.max_pe:
            return False, f"P/E {fund.pe:.0f} > {gates.max_pe:.0f}"
    if fund.debt_equity is not None and fund.debt_equity > gates.max_debt_equity:
        return False, f"D/E {fund.debt_equity:.1f} > {gates.max_debt_equity:.1f}"
    return True, ""


def _ramp(value: float | None, low: float, high: float) -> float | None:
    """Linear 0..1 as value goes low->high (clamped). None passes through."""
    if value is None:
        return None
    if high == low:
        return 1.0 if value >= high else 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _fundamental_score(fund) -> float:
    """Blend value + quality + growth into 0..1; missing dimensions stay neutral."""
    if fund is None:
        return 0.5

    # Value: cheaper is better. Prefer PEG, fall back to P/E.
    if fund.peg is not None:
        value = 1.0 - (_ramp(fund.peg, 1.0, 3.0) or 0.0)   # PEG 1 -> 1.0, 3 -> 0
    elif fund.pe is not None and fund.pe > 0:
        value = 1.0 - (_ramp(fund.pe, 15.0, 50.0) or 0.0)  # P/E 15 -> 1.0, 50 -> 0
    else:
        value = None

    # Quality: return on equity + net margin.
    quality = _mean_present(_ramp(fund.roe, 0.0, 25.0), _ramp(fund.net_margin, 0.0, 20.0))
    # Growth: forward EPS growth + trailing sales growth.
    growth = _mean_present(_ramp(fund.eps_growth, 0.0, 25.0), _ramp(fund.sales_growth, 0.0, 20.0))

    return _mean_present(value, quality, growth, default=0.5)


def _mean_present(*values, default: float = 0.5) -> float:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else default


class ConvictionScorer:
    """Blend the screeners into one 0-100 Daily Conviction Score per stock."""

    def __init__(self, weights: dict | None = None, gates: Gates | None = None,
                 vol_window: int = 63):
        self.weights = weights or DEFAULT_WEIGHTS
        self.gates = gates or Gates()
        self.vol_window = vol_window

    def score(self, ticker: str, sector: str | None, df: pd.DataFrame,
              sector_ctx: dict[str, dict], fund=None) -> dict[str, Any] | None:
        """Score one stock. Returns None if there isn't enough data to judge.

        ``fund`` is an optional Fundamentals record; when absent the fundamental
        factor stays neutral and the fundamental gate is skipped.
        """
        if df.empty or "Close" not in df.columns or len(df) < 60:
            return None

        liq_ok, gate_reason = _liquidity_ok(df, self.gates)
        if not liq_ok:
            return {"ticker": ticker, "sector": sector, "liquidity_ok": False,
                    "score": None, "reason": f"filtered: {gate_reason}"}

        fund_ok, fund_reason = _fundamental_gate(fund, self.gates)
        if not fund_ok:
            return {"ticker": ticker, "sector": sector, "liquidity_ok": True,
                    "gated": True, "score": None, "reason": f"filtered: {fund_reason}"}

        close = df["Close"]
        price = float(close.iloc[-1])
        daily = close.pct_change().dropna() * 100.0
        vol = float(daily.iloc[-self.vol_window:].std()) if len(daily) else 0.0

        r3 = _return_pct(close, 63)
        r6 = _return_pct(close, 126)
        r12 = _return_pct(close, 252)

        sma50 = float(df["SMA_50"].iloc[-1]) if "SMA_50" in df and pd.notna(df["SMA_50"].iloc[-1]) else None
        sma200 = float(df["SMA_200"].iloc[-1]) if "SMA_200" in df and pd.notna(df["SMA_200"].iloc[-1]) else None

        ctx = sector_ctx.get(sector, {})
        quadrant = ctx.get("quadrant", "n/a")
        sector_r3 = ctx.get("ret_3m")

        f_sector = QUADRANT_TAILWIND.get(quadrant, 0.5)
        f_trend = _trend_score(r3, r6, r12, price, sma50, sma200)
        f_rel = _rel_strength_score(r3, sector_r3)
        f_vol = _volatility_fit(vol)
        f_trigger, fired = _triggers(df)
        f_fundamental = _fundamental_score(fund)

        factors = {
            "sector": f_sector, "trend": f_trend, "rel_strength": f_rel,
            "volatility": f_vol, "trigger": f_trigger, "fundamental": f_fundamental,
        }
        composite = sum(self.weights[k] * factors[k] for k in self.weights) * 100.0

        return {
            "ticker": ticker,
            "sector": sector,
            "liquidity_ok": True,
            "score": round(composite, 1),
            "price": round(price, 2),
            "quadrant": quadrant,
            "daily_vol": round(vol, 2),
            "ret_3m": round(r3, 1) if r3 is not None else None,
            "ret_6m": round(r6, 1) if r6 is not None else None,
            "ret_12m": round(r12, 1) if r12 is not None else None,
            "rel_sector_3m": round(r3 - sector_r3, 1) if (r3 is not None and sector_r3 is not None) else None,
            # Fundamental display fields (None when unavailable).
            "pe": _round(getattr(fund, "pe", None), 1),
            "peg": _round(getattr(fund, "peg", None), 2),
            "roe": _round(getattr(fund, "roe", None), 1),
            "eps_growth": _round(getattr(fund, "eps_growth", None), 1),
            "debt_equity": _round(getattr(fund, "debt_equity", None), 2),
            "market_cap": getattr(fund, "market_cap", None),
            "factors": {k: round(v, 2) for k, v in factors.items()},
            "triggers": fired,
            "reason": self._reason(quadrant, r12, r3, sector_r3, fired, fund),
        }

    @staticmethod
    def _reason(quadrant, r12, r3, sector_r3, fired, fund=None) -> str:
        parts: list[str] = []
        if quadrant in ("Leading", "Improving"):
            parts.append(f"{quadrant} sector")
        if r12 is not None and r12 > 0:
            parts.append(f"+{r12:.0f}% 12M")
        if r3 is not None and sector_r3 is not None and (r3 - sector_r3) > 0:
            parts.append(f"beats sector +{r3 - sector_r3:.0f}%")
        if fired:
            parts.append(", ".join(fired))
        if fund is not None:
            if fund.roe is not None and fund.roe >= 20:
                parts.append(f"ROE {fund.roe:.0f}%")
            if fund.peg is not None and 0 < fund.peg <= 1.2:
                parts.append(f"PEG {fund.peg:.1f}")
        return " · ".join(parts) if parts else "no standout factors"


def _round(value, ndigits):
    return round(value, ndigits) if isinstance(value, (int, float)) else None
