"""Stateful virtual-portfolio replay of the MidSmallcap dual-horizon strategy.

The stateless :mod:`screener.screeners.dual_momentum_rotation` can flag *what to
buy today*, but it has no memory — so it cannot tell you the price a name was
bought at, its trailing-stop level, or whether a sold name is now past its rebuy
cooldown. Those all need a running portfolio.

This module *replays* the backtrader ``SkeletonStrategy`` (branch ``autostratdev/jul3``,
commit ``75e9b28``) faithfully over the price history we already fetch, maintaining a
virtual book: which names are held, each position's entry price and post-entry peak,
and each sold name's rebuy cooldown. Run to the latest bar, it reports three things:

* **held**   — the ≤20 names the strategy currently owns, with entry (buy) price, the
  current trailing-stop level (``peak × (1 − trail)``), and open gain.
* **sold**   — names exited within the last ``RECENT_SELL_DAYS`` bars, with the entry
  price, exit price, realised gain and the exit reason (``days_ago == 0`` is *today*).
* **rebuys** — names off cooldown that re-qualify for the top-20 but aren't held, with
  the earlier entry price for reference.

Capital is not modelled: the strategy is equal-weight (``value / top_n × 0.98`` per
slot ≈ 4.9% each), so the *set* of holdings — all these signals need — is independent
of the account size. Share counts would need a portfolio value; the weight is a
constant surfaced in the UI instead.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Ported verbatim from SkeletonStrategy.params (Exp 37, branch autostratdev/jul3).
MOMENTUM_PERIOD = 189      # long momentum look-back
HORIZON_MID = 63           # medium horizon added to the score
MOMENTUM_SKIP = 10         # bars skipped off the recent end
TREND_PERIOD = 150         # SMA gating entry and exit
TOP_N = 20                 # target holdings
REBALANCE_EVERY = 5        # bars between ranking passes
HOLD_BUFFER_MULT = 2       # keep holdings while ranked in the top TOP_N * mult
TRAIL_PCT = 0.15           # trailing stop below the post-entry peak close
COOLDOWN_BARS = 10         # bars to wait before rebuying a sold name
SLOT_FRAC = 0.98           # cash buffer -> per-slot weight is SLOT_FRAC / TOP_N

RECENT_SELL_DAYS = 21      # how far back the "recently sold" view looks

WEIGHT_PCT = round(SLOT_FRAC / TOP_N * 100, 1)   # equal-weight sizing, ≈ 4.9%


@dataclass
class HeldName:
    ticker: str
    entry_price: float
    entry_date: str           # when the strategy entered (buy signal date)
    current_price: float
    stop_loss: float          # peak * (1 - TRAIL_PCT), the live trailing stop
    gain_pct: float
    days_held: int            # trading days held so far


@dataclass
class SoldName:
    ticker: str
    entry_price: float
    entry_date: str           # when the (now-closed) position was entered
    exit_price: float
    gain_pct: float
    reason: str
    days_ago: int             # 0 == exited on the latest bar ("sell now")


@dataclass
class RebuyName:
    ticker: str
    prev_entry_price: float    # the entry of the position that was sold
    current_price: float


@dataclass
class PortfolioResult:
    held: list[HeldName]
    sold: list[SoldName]
    rebuys: list[RebuyName]


@dataclass
class _Position:
    entry_price: float
    entry_idx: int
    peak: float


def _momentum_at(col: pd.Series, i: int) -> float | None:
    """Dual-horizon momentum on bar ``i`` (positional), or None if unavailable.

    Backtrader ``close[-k]`` at the current bar maps to ``iloc[i - k]`` here.
    """
    if i < MOMENTUM_PERIOD:
        return None
    past = col.iloc[i - MOMENTUM_PERIOD]
    mid = col.iloc[i - HORIZON_MID]
    recent = col.iloc[i - MOMENTUM_SKIP]
    if pd.isna(past) or pd.isna(mid) or pd.isna(recent) or past <= 0 or mid <= 0:
        return None
    return (recent / past - 1.0) + (recent / mid - 1.0)


def _last_valid(col: pd.Series) -> float | None:
    v = col.dropna()
    return float(v.iloc[-1]) if len(v) else None


def _date_str(label) -> str:
    """ISO date for a panel index label (a Timestamp on real data)."""
    try:
        return label.date().isoformat()
    except AttributeError:
        return str(label)


def simulate(closes: dict[str, pd.Series]) -> PortfolioResult:
    """Replay the strategy over aligned close series and report the book at the end."""
    closes = {t: s for t, s in closes.items() if s is not None and not s.dropna().empty}
    if not closes:
        return PortfolioResult([], [], [])

    panel = pd.DataFrame(closes).sort_index()
    sma = panel.rolling(TREND_PERIOD, min_periods=TREND_PERIOD).mean()
    dates = panel.index
    n = len(dates)

    held: dict[str, _Position] = {}
    cooldown_until: dict[str, int] = {}
    last_entry: dict[str, float] = {}          # most recent entry price, kept after a sale
    exits: dict[str, tuple] = {}  # ticker -> (exit_idx, entry_idx, entry, exit, reason)
    last_ranked: list[str] = []

    for i in range(n):
        row = panel.iloc[i]
        smarow = sma.iloc[i]

        # ---- Daily exits: trend break (below SMA150) or trailing stop ----
        for sym in list(held):
            px = row[sym]
            if pd.isna(px):
                continue
            pos = held[sym]
            pos.peak = max(pos.peak, px)
            sm = smarow[sym]
            trend_break = (not pd.isna(sm)) and px < sm
            stop_hit = px < pos.peak * (1.0 - TRAIL_PCT)
            if trend_break or stop_hit:
                reason = ("trend break + stop" if trend_break and stop_hit
                          else "trailing stop" if stop_hit else "trend break")
                exits[sym] = (i, pos.entry_idx, pos.entry_price, float(px), reason)
                del held[sym]
                cooldown_until[sym] = i + COOLDOWN_BARS

        # ---- Weekly rebalance: rank, drop from buffer, fill free slots ----
        if i % REBALANCE_EVERY == 0 and i >= MOMENTUM_PERIOD:
            scores: dict[str, float] = {}
            for sym in panel.columns:
                px = row[sym]
                sm = smarow[sym]
                if pd.isna(px) or pd.isna(sm) or px <= sm:   # eligibility: above SMA150
                    continue
                m = _momentum_at(panel[sym], i)
                if m is not None and m > 0:
                    scores[sym] = m
            ranked = sorted(scores, key=scores.get, reverse=True)
            last_ranked = ranked
            hold_buffer = set(ranked[:TOP_N * HOLD_BUFFER_MULT])

            for sym in list(held):                           # sell out of the buffer
                if sym not in hold_buffer:
                    px = row[sym]
                    if pd.isna(px):
                        continue
                    exits[sym] = (i, held[sym].entry_idx, held[sym].entry_price,
                                  float(px), "dropped from top 40")
                    del held[sym]
                    cooldown_until[sym] = i + COOLDOWN_BARS

            slots = TOP_N - len(held)
            for sym in ranked[:TOP_N]:                       # fill with top-ranked entrants
                if slots <= 0:
                    break
                if sym in held or i < cooldown_until.get(sym, 0):
                    continue
                px = row[sym]
                if pd.isna(px):
                    continue
                held[sym] = _Position(entry_price=float(px), entry_idx=i, peak=float(px))
                last_entry[sym] = float(px)
                exits.pop(sym, None)                          # re-entered: no longer "sold"
                slots -= 1

    last = n - 1
    held_out: list[HeldName] = []
    for sym, pos in held.items():
        cur = _last_valid(panel[sym])
        if cur is None:
            continue
        peak = max(pos.peak, cur)
        held_out.append(HeldName(
            ticker=sym, entry_price=round(pos.entry_price, 2),
            entry_date=_date_str(dates[pos.entry_idx]), current_price=round(cur, 2),
            stop_loss=round(peak * (1.0 - TRAIL_PCT), 2),
            gain_pct=round((cur / pos.entry_price - 1.0) * 100.0, 1),
            days_held=last - pos.entry_idx,
        ))

    sold_out: list[SoldName] = []
    for sym, (idx, entry_idx, entry, exit_px, reason) in exits.items():
        days_ago = last - idx
        if days_ago > RECENT_SELL_DAYS:
            continue
        sold_out.append(SoldName(
            ticker=sym, entry_price=round(entry, 2), entry_date=_date_str(dates[entry_idx]),
            exit_price=round(exit_px, 2),
            gain_pct=round((exit_px / entry - 1.0) * 100.0, 1),
            reason=reason, days_ago=days_ago,
        ))

    rebuys_out: list[RebuyName] = []
    for sym in last_ranked[:TOP_N]:                          # off cooldown, re-qualified, not held
        if sym in held or sym not in last_entry or last < cooldown_until.get(sym, 0):
            continue
        cur = _last_valid(panel[sym])
        if cur is None:
            continue
        rebuys_out.append(RebuyName(
            ticker=sym, prev_entry_price=round(last_entry[sym], 2), current_price=round(cur, 2),
        ))

    held_out.sort(key=lambda h: h.gain_pct, reverse=True)
    sold_out.sort(key=lambda s: s.days_ago)
    return PortfolioResult(held_out, sold_out, rebuys_out)
