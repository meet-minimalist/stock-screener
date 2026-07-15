from __future__ import annotations

from screener.records import StockRecord
from screener.screens import SCREENS_BY_KEY, apply_screen


def _rec(ticker, score=70.0, **kw):
    return StockRecord(ticker=ticker, score=score, **kw)


def test_signal_backed_screens_select_buys():
    records = [
        _rec("A", signals={"volatile_uptrend": "BUY"}),
        _rec("B", signals={"volatile_uptrend": "NEUTRAL"}),
        _rec("C", signals={"golden_cross": "BUY"}),
    ]
    vol = apply_screen(SCREENS_BY_KEY["volatile_uptrend"], records)
    assert [r.ticker for r in vol] == ["A"]
    gc = apply_screen(SCREENS_BY_KEY["golden_cross"], records)
    assert [r.ticker for r in gc] == ["C"]


def test_composite_screens_use_record_fields():
    records = [
        _rec("LEAD", quadrant="Leading"),
        _rec("LAG", quadrant="Lagging"),
        _rec("QC", roe=25, eps_growth=10, debt_equity=0.5),
        _rec("JUNK", roe=5, eps_growth=-3, debt_equity=4.0),
    ]
    leaders = apply_screen(SCREENS_BY_KEY["sector_leaders"], records)
    assert {r.ticker for r in leaders} == {"LEAD"}
    quality = apply_screen(SCREENS_BY_KEY["quality_compounders"], records)
    assert {r.ticker for r in quality} == {"QC"}


def test_top_picks_sorted_by_score_desc():
    records = [_rec("A", score=60), _rec("B", score=90), _rec("C", score=75)]
    top = apply_screen(SCREENS_BY_KEY["top_picks"], records)
    assert [r.ticker for r in top] == ["B", "C", "A"]


def test_gated_records_excluded_from_passed_screens():
    gated = StockRecord(ticker="X", score=None, filtered=True, quadrant="Leading")
    assert apply_screen(SCREENS_BY_KEY["sector_leaders"], [gated]) == []
