"""Dual-horizon momentum rotation over the NIFTY MidSmallcap 400, as a screener signal.

Ported from the backtrader ``SkeletonStrategy`` on the ``autostratdev/jul3`` branch
(commit ``75e9b28``, "Exp 37: dual-horizon momentum"). Like the S&P quad-horizon
rotation, only the *selection* logic maps onto a market-wide screener; the strategy's
position-management mechanics (the 15% trailing stop, rebuy cooldowns, slot sizing)
need a live portfolio's per-position state and are intentionally omitted.

What differs from :mod:`screener.screeners.momentum_rotation`:

- **Dual-horizon momentum** — ``(close[-10]/close[-189] - 1) + (close[-10]/close[-63] - 1)``:
  a long (189-bar) plus a medium (63-bar) return, both measured up to 10 bars back
  (the short skip that avoids recent-reversal noise).
- **One trend SMA (150)** gates *both* entry and exit — there is no separate slower
  exit SMA.
- **Universe-scoped** — ranked only within the NIFTY MidSmallcap 400 constituents
  (Midcap 150 + Smallcap 250), a subset already scanned by the India run.

Two stages, matching the strategy:

1. :func:`compute_metrics` — per-stock, inside the daily loop (needs only that
   stock's close history): the dual-horizon score plus the SMA150 trend level.
2. :func:`assign_signals` — cross-sectional, once after the loop: rank the MidSmallcap
   400 members by momentum and turn each into BUY / SELL / NEUTRAL.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Ported verbatim from SkeletonStrategy.params (Exp 37).
HORIZON_LONG = 189        # momentum_period — long look-back
HORIZON_MID = 63          # the added medium horizon
SKIP_DAYS = 10            # momentum_skip — bars skipped off the recent end
SMA_PERIOD = 150          # trend filter: gates both entry and exit
TOP_N = 20                # target holdings -> size of the BUY list
HOLD_BUFFER = 2.0         # a name is a plausible holding while rank <= TOP_N * HOLD_BUFFER

SIGNAL_KEY = "dual_momentum_rotation"
UNIVERSE = "nifty_midsmallcap400"          # the index this strategy ranks within

# Longest look-back the momentum needs: close[-HORIZON_LONG] must exist, i.e. the
# frame must be longer than HORIZON_LONG (the strategy's ``len(d) <= momentum_period``
# guard).
_MAX_LOOKBACK = HORIZON_LONG


@dataclass
class DualMomentumMetrics:
    """One stock's dual-horizon momentum + trend snapshot on the latest bar."""
    momentum: float          # dual-horizon score (can be negative)
    price: float             # latest close
    sma: float | None        # SMA150 (entry & exit trend); None if < SMA_PERIOD bars


def compute_metrics(df: pd.DataFrame) -> DualMomentumMetrics | None:
    """Per-stock dual-horizon momentum + trend snapshot, or ``None`` if too short.

    Mirrors ``SkeletonStrategy._momentum``: ``recent = close[-10]``,
    ``past = close[-189]``, ``mid = close[-63]``, score ``= recent/past - 1 +
    recent/mid - 1``. Backtrader's ``close[-k]`` maps to pandas ``close.iloc[-1 - k]``
    (``iloc[-1]`` is the latest bar).
    """
    if df.empty or "Close" not in df.columns or len(df) <= _MAX_LOOKBACK:
        return None
    close = df["Close"].astype(float)
    past = close.iloc[-1 - HORIZON_LONG]
    mid = close.iloc[-1 - HORIZON_MID]
    recent = close.iloc[-1 - SKIP_DAYS]
    if past <= 0 or mid <= 0:
        return None
    momentum = (recent / past - 1.0) + (recent / mid - 1.0)
    return DualMomentumMetrics(
        momentum=float(momentum),
        price=float(close.iloc[-1]),
        sma=_sma(close, SMA_PERIOD),
    )


def _sma(close: pd.Series, period: int) -> float | None:
    if len(close) < period:
        return None
    val = close.rolling(period).mean().iloc[-1]
    return float(val) if pd.notna(val) else None


def assign_signals(metrics: dict[str, DualMomentumMetrics],
                   membership: set[str]) -> dict[str, str]:
    """Cross-sectional BUY / SELL / NEUTRAL per ticker, ranked within ``membership``.

    Only names in ``membership`` (the NIFTY MidSmallcap 400) are ranked and signalled;
    everything else is absent from the result.

    - **BUY**  — an eligible member (close >= SMA150, positive momentum) ranked in the
      top ``TOP_N`` by momentum within the index: the strategy's buy list.
    - **SELL** — a *plausible holding* (still top ``TOP_N * HOLD_BUFFER`` by momentum)
      that has closed **below its SMA150** — this strategy's trend-break exit (entry
      and exit share the 150-day SMA).
    - **NEUTRAL** — other members (including the hold-buffer zone that is neither a
      fresh buy nor a break).
    """
    m = {sym: mm for sym, mm in metrics.items() if sym in membership}

    positive = {sym: mm.momentum for sym, mm in m.items() if mm.momentum > 0}
    ranked = sorted(positive, key=positive.get, reverse=True)
    rank_of = {sym: i + 1 for i, sym in enumerate(ranked)}
    keep_rank = int(TOP_N * HOLD_BUFFER)

    eligible = [sym for sym in ranked
                if m[sym].sma is not None and m[sym].price >= m[sym].sma]
    buys = set(eligible[:TOP_N])

    signals: dict[str, str] = {}
    for sym, mm in m.items():
        rank = rank_of.get(sym)
        if sym in buys:
            signals[sym] = "BUY"
        elif (rank is not None and rank <= keep_rank
              and mm.sma is not None and mm.price < mm.sma):
            signals[sym] = "SELL"
        else:
            signals[sym] = "NEUTRAL"
    return signals
