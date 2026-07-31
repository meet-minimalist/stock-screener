from __future__ import annotations

import numpy as np
import pandas as pd

from screener.screeners import momentum_portfolio as mp


def _series(prices: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    return pd.Series(prices, index=idx, dtype=float)


def _rising(n: int, rate: float, start: float = 100.0) -> list[float]:
    return [start * (1.0 + rate) ** i for i in range(n)]


def test_held_name_reports_entry_stop_and_gain():
    n = 260
    win = _rising(n, 0.004)                       # monotonic riser -> bought and held
    res = mp.simulate({"WIN": _series(win), "OTHER": _series(_rising(n, 0.003))})
    held = {h.ticker: h for h in res.held}
    assert "WIN" in held
    h = held["WIN"]
    assert h.entry_price == round(win[190], 2)               # entered at the first rebalance ≥189
    assert h.current_price == round(win[-1], 2)
    assert h.stop_loss == round(win[-1] * (1 - mp.TRAIL_PCT), 2)   # trails the (rising) peak
    assert h.gain_pct > 0
    assert h.days_held == (n - 1) - 190


def test_trailing_stop_exit_shows_up_as_recently_sold():
    n = 260
    # Rise, then a sharp drop near the end -> trailing-stop exit within the recent window.
    prices = _rising(249, 0.004)
    last = prices[-1]
    prices += [last * (1 - 0.05) ** k for k in range(1, n - 249 + 1)]   # ~5%/day fall
    res = mp.simulate({"STOP": _series(prices), "WIN": _series(_rising(n, 0.004))})
    sold = {s.ticker: s for s in res.sold}
    assert "STOP" in sold
    s = sold["STOP"]
    assert s.reason == "trailing stop"
    assert s.entry_price == round(prices[190], 2)
    assert 0 <= s.days_ago <= mp.RECENT_SELL_DAYS
    assert "STOP" not in {h.ticker for h in res.held}          # no longer held


def test_names_below_their_sma_are_never_bought():
    n = 260
    declining = [100.0 * (0.999) ** i for i in range(n)]       # always under a lagging SMA150
    res = mp.simulate({"LOW": _series(declining), "WIN": _series(_rising(n, 0.004))})
    names = {h.ticker for h in res.held} | {s.ticker for s in res.sold}
    assert "LOW" not in names


def test_old_exits_fall_outside_the_recent_window():
    n = 300
    # Drop early (well over RECENT_SELL_DAYS ago), then flat -> exit is old, not reported.
    prices = _rising(210, 0.004)
    lastp = prices[-1]
    prices += [lastp * (1 - 0.05) ** k for k in range(1, 11)]   # crash around bar ~215
    prices += [prices[-1]] * (n - len(prices))                  # flat to the end
    res = mp.simulate({"OLD": _series(prices), "WIN": _series(_rising(n, 0.004))})
    assert "OLD" not in {s.ticker for s in res.sold}            # exit is > RECENT_SELL_DAYS ago


def test_rebuy_opportunity_when_slot_is_full(monkeypatch):
    # One slot, buffer keeps holdings, so a stopped-out leader that recovers while the
    # slot is taken shows up as a rebuy rather than being re-bought.
    monkeypatch.setattr(mp, "TOP_N", 1)
    monkeypatch.setattr(mp, "HOLD_BUFFER_MULT", 5)     # held name never dropped on rank
    n = 460
    # X: strong riser -> crash -> long recovery. A: steady modest riser (fills the slot).
    x = _rising(250, 0.010)
    x += [x[-1] * (1 - 0.04) ** k for k in range(1, 21)]        # crash ~20 bars
    x += [x[-1] * (1 + 0.02) ** k for k in range(1, n - len(x) + 1)]   # strong recovery
    a = _rising(n, 0.003)
    res = mp.simulate({"X": _series(x), "A": _series(a)})
    held = {h.ticker for h in res.held}
    rebuys = {r.ticker: r for r in res.rebuys}
    assert "A" in held                                 # steady name occupies the one slot
    assert "X" in rebuys                               # recovered leader, off cooldown, slot full
    assert rebuys["X"].prev_entry_price == round(x[190], 2)


def test_weight_is_equal_and_empty_input_is_safe():
    assert mp.WEIGHT_PCT == round(mp.SLOT_FRAC / mp.TOP_N * 100, 1)
    empty = mp.simulate({})
    assert (empty.held, empty.sold, empty.rebuys) == ([], [], [])
