from __future__ import annotations

import numpy as np
import pandas as pd

from screener.fundamentals.schema import Fundamentals
from screener.indicators.calculator import IndicatorCalculator
from screener.scoring import (
    ConvictionScorer,
    Gates,
    _fundamental_gate,
    _fundamental_score,
)


def _fund(**kw):
    base = dict(ticker="X", as_of="2026-07-14")
    base.update(kw)
    return Fundamentals(**base)


def test_fundamental_gate_missing_never_fails():
    assert _fundamental_gate(None, Gates())[0] is True
    assert _fundamental_gate(_fund(), Gates())[0] is True  # all None


def test_fundamental_gate_rejects_weak_names():
    assert _fundamental_gate(_fund(pe=-3), Gates())[0] is False       # money-loser
    assert _fundamental_gate(_fund(pe=120), Gates())[0] is False      # over max_pe
    assert _fundamental_gate(_fund(debt_equity=4.0), Gates())[0] is False
    assert _fundamental_gate(_fund(pe=22, debt_equity=1.0), Gates())[0] is True


def test_fundamental_score_ranks_quality_over_junk():
    strong = _fund(peg=0.8, roe=30, net_margin=25, eps_growth=30, sales_growth=25)
    weak = _fund(peg=3.5, roe=2, net_margin=1, eps_growth=-5, sales_growth=0)
    assert _fundamental_score(strong) > 0.8
    assert _fundamental_score(weak) < 0.2
    assert _fundamental_score(None) == 0.5          # unknown -> neutral
    assert _fundamental_score(_fund()) == 0.5       # all missing -> neutral


def _synthetic_df(n=260, up=True):
    idx = pd.date_range("2024-06-01", periods=n, freq="B")
    trend = np.linspace(0, 0.6, n) if up else np.linspace(0.6, 0, n)
    close = 100 * (1 + trend) + np.sin(np.arange(n) / 5)
    df = pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99,
         "Close": close, "Volume": np.full(n, 5_000_000.0)},
        index=idx,
    )
    return IndicatorCalculator().compute(
        df, sma_periods=[50, 200], macd_config={"fast": 12, "slow": 26, "signal": 9}
    )


def test_scorer_includes_fundamentals_and_gates():
    scorer = ConvictionScorer()
    df = _synthetic_df()
    ctx = {"Information Technology": {"quadrant": "Leading", "etf": "XLK", "ret_3m": 5.0}}

    good = _fund(pe=25, peg=1.0, roe=30, net_margin=20, eps_growth=25,
                 sales_growth=15, debt_equity=0.5)
    res = scorer.score("AAA", "Information Technology", df, ctx, fund=good)
    assert res is not None and res.score is not None and res.passed
    assert "fundamental" in res.factors
    assert res.pe == 25 and res.roe == 30

    # A gated name (over-levered) is dropped: score None.
    gated = scorer.score("BBB", "Information Technology", df, ctx,
                         fund=_fund(pe=20, debt_equity=5.0))
    assert gated is not None and gated.score is None and gated.filtered

    # Same stock scores higher with strong fundamentals than with weak ones.
    weak = _fund(pe=70, peg=3.0, roe=1, net_margin=1, eps_growth=-10, sales_growth=0)
    hi = scorer.score("AAA", "Information Technology", df, ctx, fund=good).score
    lo = scorer.score("AAA", "Information Technology", df, ctx, fund=weak).score
    assert hi > lo
