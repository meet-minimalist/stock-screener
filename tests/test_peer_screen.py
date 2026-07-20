from __future__ import annotations

from screener.fundamental_screener import SCREENS, build_rows
from screener.fundamentals.schema import Fundamentals


def _stock(ticker, sector, ps, net_margin=10.0, debt_equity=0.3):
    # Enough metrics that grade() returns an overall score (so the row is kept).
    return Fundamentals(
        ticker=ticker, as_of="2026-07-20", sector=sector,
        pe=15.0, ps=ps, pb=3.0, roe=15.0, net_margin=net_margin,
        eps_growth=10.0, debt_equity=debt_equity,
    )


def _build():
    funds = {f.ticker: f for f in [
        _stock("CHEAP", "Tech", 1.0),
        _stock("MID", "Tech", 2.0),
        _stock("FAIR", "Tech", 3.0),
        _stock("PEER1", "Tech", 3.0),
        _stock("PEER2", "Tech", 3.0),
        _stock("EXPENSIVE", "Tech", 10.0),           # too dear vs sector
        _stock("THIN", "Tech", 1.0, net_margin=1.0),  # fails the 2% margin floor
        _stock("LEVERED", "Tech", 1.0, debt_equity=3.0),  # fails the leverage gate
        _stock("SOLO", "Utilities", 1.0),            # lone name → no sector median
    ]}
    rows, screen_meta = build_rows(funds)
    return {r["ticker"]: r for r in rows}, {m["key"]: m for m in screen_meta}


def test_rel_ps_is_sector_relative():
    rows, _ = _build()
    # Tech P/S = [1,2,3,3,3,10,1,1] → median 2.5; rel_ps = ps / 2.5.
    assert rows["CHEAP"]["rel_ps"] == 1.0 / 2.5
    assert rows["EXPENSIVE"]["rel_ps"] == 10.0 / 2.5
    # A sector with fewer than the minimum peers gets no benchmark.
    assert rows["SOLO"]["rel_ps"] is None


def test_cheap_vs_peers_membership_and_gates():
    rows, meta = _build()
    members = {t for t, r in rows.items() if "cheap_vs_peers" in r["screens"]}
    assert {"CHEAP", "MID", "FAIR", "PEER1", "PEER2"} == members
    assert "EXPENSIVE" not in members    # rel P/S above 1.5x sector median
    assert "THIN" not in members         # net margin below 2%
    assert "LEVERED" not in members      # debt/equity above the gate
    assert "SOLO" not in members         # no sector benchmark
    assert meta["cheap_vs_peers"]["count"] == 5


def test_cheap_vs_peers_ranks_ascending():
    # The screen sorts by rel_ps ascending so the cheapest-vs-peers surface first.
    screen = next(s for s in SCREENS if s.key == "cheap_vs_peers")
    assert screen.sort_by == "rel_ps" and screen.sort_desc is False
