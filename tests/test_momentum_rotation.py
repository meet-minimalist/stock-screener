from __future__ import annotations

import pandas as pd
import pytest

from screener.screeners import momentum_rotation as mr
from screener.screeners.momentum_rotation import MomentumMetrics


def _geometric_closes(n: int, g: float) -> pd.DataFrame:
    """A clean (1+g)**i close series so momentum ratios are exact powers of (1+g)."""
    close = pd.Series([(1.0 + g) ** i for i in range(n)])
    return pd.DataFrame({"Close": close, "Volume": [1_000_000] * n})


def test_compute_metrics_needs_enough_history():
    assert mr.compute_metrics(_geometric_closes(mr._MAX_LOOKBACK, 0.001)) is None
    assert mr.compute_metrics(_geometric_closes(mr._MAX_LOOKBACK + 1, 0.001)) is not None


def test_compute_metrics_matches_the_quad_horizon_formula():
    g = 0.001
    df = _geometric_closes(300, g)
    m = mr.compute_metrics(df)
    # On a (1+g)**i series, base/past over horizon h is exactly (1+g)**h.
    expected = sum(w * ((1.0 + g) ** h - 1.0) for h, w in mr.HORIZONS)
    assert m is not None
    assert m.momentum == pytest.approx(expected)
    assert m.price == pytest.approx((1.0 + g) ** 299)
    # A rising series sits above both trailing SMAs.
    assert m.sma is not None and m.price > m.sma
    assert m.exit_sma is not None and m.price > m.exit_sma


def test_compute_metrics_short_history_leaves_smas_none():
    # Enough for the momentum lookback (212) but short of SMA250.
    m = mr.compute_metrics(_geometric_closes(230, 0.001))
    assert m is not None
    assert m.sma is not None          # 150-day SMA available
    assert m.exit_sma is None         # 250-day SMA not yet


def test_assign_signals_buys_top_n_eligible_and_holds_the_buffer():
    # 25 eligible, descending-momentum names above their SMAs, no trend break.
    metrics = {f"T{i:02d}": MomentumMetrics(momentum=100.0 - i, price=100.0,
                                            sma=90.0, exit_sma=80.0)
               for i in range(25)}
    sig = mr.assign_signals(metrics)
    assert sig["T00"] == "BUY"                    # strongest
    assert sig[f"T{mr.TOP_N - 1:02d}"] == "BUY"   # last of the top 20
    assert sig[f"T{mr.TOP_N:02d}"] == "NEUTRAL"   # rank 21 — in the hold buffer, not a buy
    assert sum(v == "BUY" for v in sig.values()) == mr.TOP_N


def test_assign_signals_excludes_below_sma150_from_the_buy_list():
    # Highest momentum of all, but trading below its entry SMA150 -> never a BUY.
    metrics = {"BELOW": MomentumMetrics(momentum=999.0, price=50.0, sma=90.0, exit_sma=40.0)}
    metrics.update({f"T{i:02d}": MomentumMetrics(momentum=100.0 - i, price=100.0,
                                                 sma=90.0, exit_sma=80.0)
                    for i in range(5)})
    sig = mr.assign_signals(metrics)
    assert sig["BELOW"] != "BUY"
    assert sig["T00"] == "BUY"


def test_assign_signals_sells_a_strong_leader_that_cracks_its_long_trend():
    metrics = {f"T{i:02d}": MomentumMetrics(momentum=100.0 - i, price=100.0,
                                            sma=90.0, exit_sma=80.0)
               for i in range(5)}
    # Rank-1 momentum but closed below SMA250 (and below SMA150 so it isn't a buy).
    metrics["CRACK"] = MomentumMetrics(momentum=500.0, price=50.0, sma=90.0, exit_sma=80.0)
    sig = mr.assign_signals(metrics)
    assert sig["CRACK"] == "SELL"


def test_sell_is_bounded_to_plausible_holdings():
    # 45 healthy strong names so anything ranked past the buffer is genuinely weak.
    metrics = {f"T{i:02d}": MomentumMetrics(momentum=100.0 - i, price=100.0,
                                            sma=90.0, exit_sma=80.0)
               for i in range(45)}
    # Positive but weakest momentum, below its SMA250: past the hold buffer -> NOT a sell.
    metrics["FADER"] = MomentumMetrics(momentum=0.5, price=50.0, sma=90.0, exit_sma=80.0)
    # Dead (non-positive) momentum below trend: never held -> NOT a sell either.
    metrics["DEAD"] = MomentumMetrics(momentum=-5.0, price=50.0, sma=90.0, exit_sma=80.0)
    sig = mr.assign_signals(metrics)
    assert sig["FADER"] == "NEUTRAL"      # rank beyond TOP_N * HOLD_BUFFER
    assert sig["DEAD"] == "NEUTRAL"       # negative momentum -> unranked, not a holding


def test_run_daily_attaches_the_momentum_rotation_signal(monkeypatch):
    """The cross-sectional signal + raw momentum must land on the scored records."""
    import screener.daily_report as dr

    rising = _geometric_closes(300, 0.02)          # strong steady uptrend
    rising["Open"] = rising["Close"]
    rising["High"] = rising["Close"] * 1.01
    rising["Low"] = rising["Close"] * 0.99
    rising.index = pd.date_range("2025-01-01", periods=len(rising), freq="B")

    class FakeFetcher:
        def __init__(self, cache_dir=None):
            pass

        def get_data(self, symbol, *a, **k):
            return rising.copy()

    monkeypatch.setattr(dr, "DataFetcher", FakeFetcher)
    monkeypatch.setattr(dr, "compute_sector_rotation", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(dr, "get_ticker_list", lambda u: ["AAA", "BBB"])
    monkeypatch.setattr(dr, "load_constituents", lambda market="us": pd.DataFrame(
        {"Symbol": ["AAA", "BBB"], "sector": ["Tech", "Tech"]}))
    monkeypatch.setattr(dr, "get_fundamentals", lambda m, t: {})

    out = dr.run_daily("2025-01-01", "2026-03-01", universe="sp500",
                       market="us", show_progress=False)
    recs = {r.ticker: r for r in out["records"]}
    assert set(recs) == {"AAA", "BBB"}
    for r in recs.values():
        assert r.signals.get(dr.MOMENTUM_ROTATION_KEY) == "BUY"   # both are top momentum
        assert r.momentum is not None
