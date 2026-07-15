from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from screener.records import StockRecord

Predicate = Callable[[StockRecord], bool]


@dataclass(frozen=True)
class Screen:
    """One browsable view: a filter over scored records, with a default sort.

    Adding a screen tab is a single entry in ``SCREENS`` below — no new code
    elsewhere. Predicates read only fields already on StockRecord (per-strategy
    ``signals``, factor scores, returns, fundamentals).
    """
    key: str
    name: str
    description: str
    predicate: Predicate
    sort_by: str = "score"
    sort_desc: bool = True


def _sig(rec: StockRecord, name: str) -> bool:
    return rec.signals.get(name) == "BUY"


def _num(value, default=0.0) -> float:
    return value if isinstance(value, (int, float)) else default


SCREENS: list[Screen] = [
    Screen("top_picks", "Top Picks",
           "Highest overall conviction across every factor.",
           lambda r: r.passed),
    # --- Momentum & breakouts ---
    Screen("volatile_uptrend", "Volatile Uptrends",
           "Lively names already trending up (3M/6M/12M positive).",
           lambda r: _sig(r, "volatile_uptrend")),
    Screen("near_52w_high", "52-Week-High Breakouts",
           "Within 3% of the 52-week high.",
           lambda r: _sig(r, "near_52w_high")),
    Screen("high_volume", "High-Volume Movers",
           "Volume at least 2x the 20-day average.",
           lambda r: _sig(r, "high_volume")),
    Screen("big_gain", "Big Gainers",
           "A large single-day advance.",
           lambda r: _sig(r, "big_gain")),
    # --- Sector-driven ---
    Screen("sector_leaders", "Sector Leaders",
           "Stocks in sectors that are Leading or Improving on the RRG.",
           lambda r: r.passed and r.quadrant in ("Leading", "Improving")),
    Screen("rs_outperformers", "RS Outperformers",
           "Beating their own sector over the last 3 months.",
           lambda r: r.passed and _num(r.rel_sector_3m) > 0),
    # --- Value & quality (fundamentals) ---
    Screen("value_momentum", "Value + Momentum",
           "Reasonable fundamentals plus positive price momentum.",
           lambda r: r.passed and _num(r.factors.get("fundamental")) >= 0.6
           and _num(r.ret_3m) > 0),
    Screen("quality_compounders", "Quality Compounders",
           "Strong returns on equity and growth with a healthy balance sheet.",
           lambda r: r.passed and _num(r.roe) >= 15 and _num(r.eps_growth) > 0
           and _num(r.debt_equity, 0.0) < 1.5),
    # --- Mean-reversion ---
    Screen("oversold_bounce", "Oversold Bounce",
           "RSI in oversold territory — potential reversal.",
           lambda r: _sig(r, "oversold_bounce")),
    Screen("pullback_uptrend", "Pullback in Uptrend",
           "Longer-term uptrend with a short-term oversold dip.",
           lambda r: _sig(r, "oversold_bounce") and _num(r.ret_12m) > 0),
    # --- Classic technical crosses ---
    Screen("bullish_macd", "Bullish MACD",
           "MACD above its signal line.",
           lambda r: _sig(r, "bullish_macd")),
    Screen("golden_cross", "Golden Cross",
           "SMA20 above SMA50.",
           lambda r: _sig(r, "golden_cross")),
    Screen("candle_patterns", "Candlestick Patterns",
           "A bullish candlestick pattern on the latest bar.",
           lambda r: _sig(r, "candle_patterns")),
]

SCREENS_BY_KEY: dict[str, Screen] = {s.key: s for s in SCREENS}


def apply_screen(screen: Screen, records: list[StockRecord]) -> list[StockRecord]:
    """Filter records by the screen and sort by its default column, high to low."""
    hits = [r for r in records if screen.predicate(r)]
    hits.sort(key=lambda r: _num(getattr(r, screen.sort_by, None), float("-inf")),
              reverse=screen.sort_desc)
    return hits
