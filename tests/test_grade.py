from __future__ import annotations

from screener.fundamentals.grade import grade
from screener.fundamentals.schema import Fundamentals


def _f(**kw):
    return Fundamentals(ticker="X", as_of="2026-07-16", **kw)


def test_strong_fundamentals_grade_high():
    g = grade(_f(pe=12, forward_pe=11, peg=0.8, ps=1.5, pb=2, pfcf=12,
                 roe=30, roa=15, roi=25, gross_margin=55, oper_margin=30, net_margin=25,
                 eps_growth=25, eps_growth_next_y=22, eps_growth_5y=20, sales_growth=18,
                 debt_equity=0.3, lt_debt_equity=0.2, current_ratio=2.5, quick_ratio=1.5))
    assert g.overall >= 80 and g.letter == "A"
    assert g.value > 70 and g.quality > 70 and g.growth > 70 and g.health > 70


def test_weak_fundamentals_grade_low():
    g = grade(_f(pe=60, forward_pe=55, peg=3.5, ps=12, pb=10, pfcf=50,
                 roe=2, roa=1, roi=1, gross_margin=10, oper_margin=2, net_margin=1,
                 eps_growth=-5, eps_growth_next_y=0, eps_growth_5y=1, sales_growth=0,
                 debt_equity=3.0, lt_debt_equity=2.5, current_ratio=0.8, quick_ratio=0.4))
    assert g.overall <= 30 and g.letter in ("D", "F")


def test_negative_pe_scores_zero_value_component():
    loss = grade(_f(pe=-5, ps=2, pb=2))
    healthy = grade(_f(pe=12, ps=2, pb=2))
    assert loss.value < healthy.value


def test_missing_dimensions_use_available():
    g = grade(_f(roe=30, net_margin=25))          # only quality metrics present
    assert g.quality is not None
    assert g.value is None and g.growth is None and g.health is None
    assert g.overall is not None                   # graded from quality alone


def test_all_missing_is_ungraded():
    g = grade(_f())
    assert g.overall is None and g.letter == "—"


def test_thin_quality_not_scored_from_single_metric():
    # A high promoter holding alone (or a lone ROE) must not mint a quality score —
    # otherwise thin-data India names float to the top of the High Quality screen.
    assert grade(_f(promoter_holding=75)).quality is None
    assert grade(_f(roe=30)).quality is None


def test_promoter_holding_is_a_light_tilt_not_a_pillar():
    # With real profitability present, promoter holding nudges quality up but doesn't
    # dominate it (15% weight).
    base = grade(_f(roe=20, net_margin=15))
    tilted = grade(_f(roe=20, net_margin=15, promoter_holding=75))
    assert base.quality is not None and tilted.quality is not None
    assert tilted.quality > base.quality
    assert tilted.quality - base.quality < 15   # bounded tilt, not an equal pillar


def test_india_shaped_record_still_grades():
    # roe/roa/roi/oper/net + ps/peg/pb + growth + debt/equity → full grade.
    g = grade(_f(pe=18, ps=3, pb=2.5, peg=1.5,
                 roe=18, roa=9, roi=16, oper_margin=20, net_margin=12,
                 eps_growth=15, eps_growth_5y=14, sales_growth=12, debt_equity=0.6,
                 promoter_holding=60))
    assert g.value is not None and g.quality is not None
    assert g.growth is not None and g.health is not None and g.overall is not None
