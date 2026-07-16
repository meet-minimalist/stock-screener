from __future__ import annotations

import pandas as pd

from screener.fundamentals.screener_in_source import _to_fundamentals, _yoy


class _FakeCompany:
    """Stands in for screener_fetcher.Company (no network)."""
    def __init__(self, top_ratios, profit_loss, balance_sheet):
        self.top_ratios = top_ratios
        self.profit_loss = profit_loss
        self.balance_sheet = balance_sheet


def _company():
    pl = pd.DataFrame(
        {"Mar 2024": [1000.0, 25.0, 120.0, 40.0],
         "Mar 2025": [1100.0, 26.0, 140.0, 44.0]},
        index=["Sales", "OPM %", "Net Profit", "EPS in Rs"],
    )
    bs = pd.DataFrame(
        {"Mar 2024": [10.0, 490.0, 250.0], "Mar 2025": [10.0, 590.0, 300.0]},
        index=["Equity Capital", "Reserves", "Borrowings"],
    )
    top = {"Market Cap": 50000.0, "Stock P/E": 20.0, "Current Price": 200.0,
           "Book Value": 100.0, "ROE": 22.0, "ROCE": 25.0, "Dividend Yield": 1.5}
    return _FakeCompany(top, pl, bs)


def test_maps_top_ratios_and_derived_fields():
    f = _to_fundamentals(_company(), "TESTCO", "2026-07-16", sector="Information Technology")
    assert f.ticker == "TESTCO" and f.sector == "Information Technology"
    assert f.pe == 20.0 and f.roe == 22.0 and f.roi == 25.0 and f.dividend_yield == 1.5
    assert f.pb == 2.0                        # 200 / 100
    assert round(f.net_margin, 2) == round(140 / 1100 * 100, 2)
    assert f.oper_margin == 26.0              # latest OPM %
    assert round(f.debt_equity, 3) == round(300 / (10 + 590), 3)
    assert round(f.eps_growth, 2) == round((44 / 40 - 1) * 100, 2)
    assert round(f.sales_growth, 2) == round((1100 / 1000 - 1) * 100, 2)


def test_yoy_handles_short_and_zero():
    assert round(_yoy([100.0, 110.0]), 6) == 10.0
    assert _yoy([50.0]) is None
    assert _yoy([0.0, 5.0]) is None          # prev == 0 -> undefined


def test_missing_statements_stay_none():
    bank = _FakeCompany(
        {"Stock P/E": 16.0, "ROE": 14.0, "ROCE": 7.0, "Current Price": 1500.0, "Book Value": 700.0},
        pd.DataFrame(), pd.DataFrame(),
    )
    f = _to_fundamentals(bank, "BANKX", "2026-07-16", sector="Financial Services")
    assert f.pe == 16.0 and f.roe == 14.0
    assert f.net_margin is None and f.sales_growth is None and f.debt_equity is None
