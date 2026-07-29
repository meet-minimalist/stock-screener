"""Cross-sectional quad-horizon momentum rotation, ported as a screener signal.

This is the *selection* half of the backtrader ``SkeletonStrategy`` (a NIFTY
champion ported to the S&P 500): score every stock by a skip-a-month, multi-horizon
momentum measure, keep the names trending above their long-term SMA, and flag the
top slice as the strategy's **buy** list. Strong-momentum names that have since
cracked their long-term trend are flagged as the **sell** list.

Only the selection logic maps onto a market-wide screener. The strategy's
*position-management* mechanics — peak-based trailing stops, rebuy cooldowns and
slot sizing — need a live portfolio's state (each holding's entry/peak), so they are
intentionally omitted here rather than faked.

Two stages, matching the strategy:

1. :func:`compute_metrics` — per-stock, run inside the daily loop (needs only that
   stock's close history): the quad-horizon momentum score plus the two trend SMAs.
2. :func:`assign_signals` — cross-sectional, run once after the loop: rank all stocks
   by momentum and turn each stock's metrics into BUY / SELL / NEUTRAL.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Ported verbatim from SkeletonStrategy.params.
HORIZONS = ((189, 1.0), (147, 1.5), (126, 1.0), (63, 1.0))
SKIP_DAYS = 21
SMA_PERIOD = 150          # entry trend filter
EXIT_SMA_PERIOD = 250     # held-position exit trend filter
TOP_N = 20                # target holdings -> size of the BUY list
HOLD_BUFFER = 2.0         # a name is a plausible holding while rank <= TOP_N * HOLD_BUFFER

SIGNAL_KEY = "momentum_rotation"

# Bars of history the longest horizon's lookback needs (base is skipped SKIP_DAYS back,
# and the oldest reference is HORIZONS-max + SKIP_DAYS bars back). Matches the
# strategy's ``max_lookback`` guard.
_MAX_LOOKBACK = max(h for h, _ in HORIZONS) + SKIP_DAYS + 1


@dataclass
class MomentumMetrics:
    """One stock's momentum + trend snapshot on the latest bar."""
    momentum: float          # quad-horizon score (can be negative)
    price: float             # latest close
    sma: float | None        # SMA150 (entry trend); None if < SMA_PERIOD bars
    exit_sma: float | None   # SMA250 (exit trend); None if < EXIT_SMA_PERIOD bars


def compute_metrics(df: pd.DataFrame) -> MomentumMetrics | None:
    """Per-stock momentum + trend snapshot, or ``None`` if history is too short.

    Mirrors ``SkeletonStrategy.momentum``: skip the most recent ``SKIP_DAYS`` bars,
    then blend weighted returns across each horizon. Backtrader's ``close[-k]`` (k bars
    back from the latest) maps to pandas ``close.iloc[-1 - k]`` since ``iloc[-1]`` is
    the latest bar.
    """
    if df.empty or "Close" not in df.columns or len(df) <= _MAX_LOOKBACK:
        return None
    close = df["Close"].astype(float)
    base = close.iloc[-1 - SKIP_DAYS]
    if base <= 0:
        return None
    score = 0.0
    for horizon, weight in HORIZONS:
        past = close.iloc[-1 - (horizon + SKIP_DAYS)]
        if past <= 0:
            return None
        score += weight * (base / past - 1.0)
    return MomentumMetrics(
        momentum=float(score),
        price=float(close.iloc[-1]),
        sma=_sma(close, SMA_PERIOD),
        exit_sma=_sma(close, EXIT_SMA_PERIOD),
    )


def _sma(close: pd.Series, period: int) -> float | None:
    if len(close) < period:
        return None
    val = close.rolling(period).mean().iloc[-1]
    return float(val) if pd.notna(val) else None


def assign_signals(metrics: dict[str, MomentumMetrics]) -> dict[str, str]:
    """Cross-sectional BUY / SELL / NEUTRAL per ticker from every stock's metrics.

    - **BUY**  — an eligible name (close >= SMA150, positive momentum) ranked in the
      top ``TOP_N`` by momentum across the universe: the strategy's buy list.
    - **SELL** — a *plausible holding* (still ranks in the top ``TOP_N * HOLD_BUFFER``
      by momentum) that has closed **below its long-term SMA250** — the strategy's
      trend-break exit. Scoping to strong-momentum names keeps this to the handful of
      former leaders rolling over, not every stock under its 250-day average.
    - **NEUTRAL** — everything else (including the rank ``TOP_N + 1 .. buffer`` hold
      zone that is neither a fresh buy nor a break).

    The peak-based trailing-stop and cooldown exits are omitted — they need
    per-position state a stateless screener does not have.
    """
    # Rank every positive-momentum name (the strategy scores only eligible names, but
    # a name that has slipped below SMA150 while still high-momentum is exactly a
    # plausible holding we want the SELL test to see, so rank the wider set here).
    positive = {sym: m.momentum for sym, m in metrics.items() if m.momentum > 0}
    ranked = sorted(positive, key=positive.get, reverse=True)
    rank_of = {sym: i + 1 for i, sym in enumerate(ranked)}
    keep_rank = int(TOP_N * HOLD_BUFFER)

    # BUY list: the top TOP_N momentum names that are above their entry SMA150.
    eligible = [sym for sym in ranked
                if metrics[sym].sma is not None and metrics[sym].price >= metrics[sym].sma]
    buys = set(eligible[:TOP_N])

    signals: dict[str, str] = {}
    for sym, m in metrics.items():
        rank = rank_of.get(sym)
        if sym in buys:
            signals[sym] = "BUY"
        elif (rank is not None and rank <= keep_rank
              and m.exit_sma is not None and m.price < m.exit_sma):
            signals[sym] = "SELL"
        else:
            signals[sym] = "NEUTRAL"
    return signals
