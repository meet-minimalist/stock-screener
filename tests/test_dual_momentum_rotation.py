from __future__ import annotations

import pandas as pd
import pytest

from screener.screeners import dual_momentum_rotation as dm
from screener.screeners.dual_momentum_rotation import DualMomentumMetrics


def _geometric_closes(n: int, g: float) -> pd.DataFrame:
    """A (1+g)**i close series so momentum ratios are exact powers of (1+g)."""
    close = pd.Series([(1.0 + g) ** i for i in range(n)])
    return pd.DataFrame({"Close": close, "Volume": [1_000_000] * n})


def test_compute_metrics_needs_more_than_the_long_horizon():
    assert dm.compute_metrics(_geometric_closes(dm.HORIZON_LONG, 0.001)) is None
    assert dm.compute_metrics(_geometric_closes(dm.HORIZON_LONG + 2, 0.001)) is not None


def test_compute_metrics_matches_the_dual_horizon_formula():
    g, n = 0.001, 260
    m = dm.compute_metrics(_geometric_closes(n, g))
    # recent/past spans (HORIZON_LONG - SKIP) bars; recent/mid spans (HORIZON_MID - SKIP).
    expected = (((1.0 + g) ** (dm.HORIZON_LONG - dm.SKIP_DAYS) - 1.0)
                + ((1.0 + g) ** (dm.HORIZON_MID - dm.SKIP_DAYS) - 1.0))
    assert m is not None
    assert m.momentum == pytest.approx(expected)
    assert m.price == pytest.approx((1.0 + g) ** (n - 1))
    assert m.sma is not None and m.price > m.sma      # rising series sits above SMA150


def test_assign_signals_only_ranks_and_signals_members():
    metrics = {f"T{i:02d}": DualMomentumMetrics(momentum=100.0 - i, price=100.0, sma=90.0)
               for i in range(25)}
    # Highest momentum of all, but not an index member -> never appears in the output.
    metrics["OUTSIDER"] = DualMomentumMetrics(momentum=999.0, price=100.0, sma=90.0)
    members = {f"T{i:02d}" for i in range(25)}
    sig = dm.assign_signals(metrics, members)
    assert "OUTSIDER" not in sig
    assert sig["T00"] == "BUY"                        # strongest member
    assert sig[f"T{dm.TOP_N:02d}"] == "NEUTRAL"       # rank 21 — hold-buffer zone
    assert sum(v == "BUY" for v in sig.values()) == dm.TOP_N


def test_assign_signals_buy_needs_close_above_sma150():
    members = {"A", "B"}
    metrics = {
        "A": DualMomentumMetrics(momentum=50.0, price=80.0, sma=90.0),   # below SMA150
        "B": DualMomentumMetrics(momentum=10.0, price=100.0, sma=90.0),  # above SMA150
    }
    sig = dm.assign_signals(metrics, members)
    assert sig["B"] == "BUY"
    assert sig["A"] != "BUY"


def test_assign_signals_sells_a_member_leader_that_breaks_sma150():
    members = {f"T{i:02d}" for i in range(5)} | {"CRACK"}
    metrics = {f"T{i:02d}": DualMomentumMetrics(momentum=100.0 - i, price=100.0, sma=90.0)
               for i in range(5)}
    # Rank-1 momentum but closed below its SMA150 (this strategy's trend-break exit).
    metrics["CRACK"] = DualMomentumMetrics(momentum=500.0, price=80.0, sma=90.0)
    sig = dm.assign_signals(metrics, members)
    assert sig["CRACK"] == "SELL"


def test_screens_are_market_scoped():
    from screener.screens import SCREENS_BY_KEY
    assert SCREENS_BY_KEY["dual_momentum_rotation"].markets == ("in",)
    assert SCREENS_BY_KEY["dual_momentum_exits"].markets == ("in",)
    assert SCREENS_BY_KEY["momentum_rotation"].markets == ("us",)


def test_payload_scopes_screens_by_market():
    from screener.records import StockRecord
    from screener.web.site import _payload
    recs = [StockRecord(ticker="AAA", score=50.0, momentum=1.0,
                        signals={"dual_momentum_rotation": "BUY", "momentum_rotation": "BUY"})]
    _, us_meta = _payload({"market": "us", "records": recs})
    _, in_meta = _payload({"market": "in", "records": recs})
    us_keys = {m["key"] for m in us_meta}
    in_keys = {m["key"] for m in in_meta}
    assert "momentum_rotation" in us_keys and "dual_momentum_rotation" not in us_keys
    assert "dual_momentum_rotation" in in_keys and "momentum_rotation" not in in_keys


def test_run_daily_india_attaches_the_dual_momentum_signal(monkeypatch):
    """India runs the dual-horizon MidSmallcap signal, not the US quad-horizon one."""
    import screener.daily_report as dr
    import screener.data.bse as bse

    rising = _geometric_closes(300, 0.02)
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
    monkeypatch.setattr(dr, "get_ticker_list", lambda u: ["AAA", "BBB"])   # universe + members
    monkeypatch.setattr(dr, "load_constituents", lambda market="us": pd.DataFrame(
        {"Symbol": ["AAA", "BBB"], "sector": ["Financials", "Financials"]}))
    monkeypatch.setattr(dr, "get_fundamentals", lambda m, t: {})
    monkeypatch.setattr(bse, "india_extra_price_universe", lambda: ([], {}, {}))

    out = dr.run_daily("2025-01-01", "2026-03-01", universe="nifty_total",
                       market="in", show_progress=False)
    recs = {r.ticker: r for r in out["records"]}
    assert set(recs) == {"AAA", "BBB"}
    for r in recs.values():
        assert r.signals.get(dr.DUAL_MOMENTUM_KEY) == "BUY"        # both are top momentum
        assert dr.MOMENTUM_ROTATION_KEY not in r.signals          # quad is US-only
        assert r.momentum is not None
