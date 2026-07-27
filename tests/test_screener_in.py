from __future__ import annotations

import sys
import types

import pandas as pd

from screener.fundamentals import screener_in_source
from screener.fundamentals.screener_in_source import _cagr, _to_fundamentals, _usable, _yoy


class _FakeCompany:
    """Stands in for screener_fetcher.Company (no network)."""
    def __init__(self, top_ratios, profit_loss, balance_sheet, shareholding=None):
        self.top_ratios = top_ratios
        self.profit_loss = profit_loss
        self.balance_sheet = balance_sheet
        self._shareholding = shareholding

    def shareholding(self, period="quarterly"):
        if self._shareholding is None:
            raise RuntimeError("no shareholding section")
        return self._shareholding


def _company():
    yrs = ["Mar 2021", "Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"]
    pl = pd.DataFrame(
        [[800, 900, 1000, 1050, 1100, 1200],   # Sales
         [24, 25, 25, 26, 26, 27],             # OPM %
         [90, 100, 120, 130, 140, 160],        # Net Profit
         [30, 34, 38, 40, 44, 50]],            # EPS in Rs
        index=["Sales", "OPM %", "Net Profit", "EPS in Rs"], columns=yrs,
    ).astype(float)
    bs = pd.DataFrame(
        {"Mar 2025": [10.0, 490.0, 250.0, 900.0], "Mar 2026": [10.0, 590.0, 300.0, 1000.0]},
        index=["Equity Capital", "Reserves", "Borrowings", "Total Assets"],
    )
    sh = pd.DataFrame({"Mar 2026": [55.2, 18.0, 15.0]}, index=["Promoters", "FIIs", "DIIs"])
    top = {"Market Cap": 50000.0, "Stock P/E": 20.0, "Current Price": 200.0,
           "Book Value": 100.0, "ROE": 22.0, "ROCE": 25.0, "Dividend Yield": 1.5}
    return _FakeCompany(top, pl, bs, shareholding=sh)


def test_maps_top_ratios_promoter_and_cagr():
    co = _company()
    f = _to_fundamentals(co, "TESTCO", "2026-07-16", sector="Information Technology")
    assert f.pe == 20.0 and f.roi == 25.0 and f.pb == 2.0
    assert round(f.net_margin, 2) == round(160 / 1200 * 100, 2)
    assert f.oper_margin == 27.0
    assert round(f.debt_equity, 3) == round(300 / (10 + 590), 3)
    # growth is multi-year CAGR, not YoY
    assert f.eps_growth == _cagr(co.profit_loss.loc["EPS in Rs"], 3)
    assert f.eps_growth_5y == _cagr(co.profit_loss.loc["EPS in Rs"], 5)
    assert f.sales_growth == _cagr(co.profit_loss.loc["Sales"], 3)
    assert f.eps_growth is not None and f.eps_growth != _yoy(co.profit_loss.loc["EPS in Rs"])
    assert f.promoter_holding == 55.2
    # Derived metrics screener.in doesn't report directly.
    assert f.ps == 50000.0 / 1200.0                  # market cap ÷ sales
    assert f.roa == 160.0 / 1000.0 * 100.0           # net profit ÷ total assets
    assert f.peg == 20.0 / f.eps_growth              # P/E ÷ EPS CAGR


def test_cagr_needs_enough_positive_periods():
    assert round(_cagr([100.0, 110.0, 121.0], 2), 6) == 10.0   # (121/100)^(1/2)-1
    assert _cagr([100.0, 110.0], 3) is None                    # too few periods
    assert _cagr([-5.0, 10.0, 20.0], 2) is None                # non-positive start


def test_missing_sections_stay_none():
    bank = _FakeCompany(
        {"Stock P/E": 16.0, "ROE": 14.0, "ROCE": 7.0, "Current Price": 1500.0, "Book Value": 700.0},
        pd.DataFrame(), pd.DataFrame(),      # no statements, no shareholding
    )
    f = _to_fundamentals(bank, "BANKX", "2026-07-16", sector="Financial Services")
    assert f.pe == 16.0 and f.roe == 14.0
    assert f.net_margin is None and f.sales_growth is None and f.promoter_holding is None
    # No statements → derived metrics can't be computed either.
    assert f.ps is None and f.peg is None and f.roa is None


def test_usable_flags_empty_consolidated_page():
    # Standalone-only filers render an empty consolidated page: a bare "₹ Cr.".
    empty = _FakeCompany({"Market Cap": "₹ Cr."}, pd.DataFrame(), pd.DataFrame())
    good = _FakeCompany({"Market Cap": 1336.0}, pd.DataFrame(), pd.DataFrame())
    assert _usable(good) is True
    assert _usable(empty) is False


class _FakeClient:
    """Records every company(slug, consolidated) call and serves canned pages."""
    def __init__(self, pages):
        self._pages = pages
        self.calls: list[tuple[str, bool]] = []

    def company(self, slug, consolidated=True):
        self.calls.append((slug, consolidated))
        return self._pages[(slug, consolidated)]


def _install_fake_client(monkeypatch, client):
    module = types.ModuleType("screener_fetcher")
    module.ScreenerClient = lambda *a, **k: client
    exc = types.ModuleType("screener_fetcher.exceptions")
    exc.ScreenerError = type("ScreenerError", (Exception,), {})
    module.exceptions = exc
    monkeypatch.setitem(sys.modules, "screener_fetcher", module)
    monkeypatch.setitem(sys.modules, "screener_fetcher.exceptions", exc)


def test_fetch_uses_alias_slug_but_records_display_ticker(monkeypatch):
    # BSE-exclusive names resolve by numeric scrip code, keyed under their ticker.
    page = _FakeCompany({"Market Cap": 16356.0, "Stock P/E": 43.1}, pd.DataFrame(), pd.DataFrame())
    client = _FakeClient({("544467", True): page})
    _install_fake_client(monkeypatch, client)

    out = screener_in_source.fetch(["NSDL"], sectors={"NSDL": "Financials"},
                                   aliases={"NSDL": "544467"})
    assert client.calls == [("544467", True)]            # fetched by scrip code
    assert set(out) == {"NSDL"}                           # recorded by display ticker
    assert out["NSDL"].ticker == "NSDL" and out["NSDL"].market_cap == 16356.0


def test_fetch_falls_back_to_standalone_when_consolidated_empty(monkeypatch):
    empty = _FakeCompany({"Market Cap": "₹ Cr."}, pd.DataFrame(), pd.DataFrame())
    standalone = _FakeCompany({"Market Cap": 1336.0, "Stock P/E": 18.5}, pd.DataFrame(), pd.DataFrame())
    client = _FakeClient({("505036", True): empty, ("505036", False): standalone})
    _install_fake_client(monkeypatch, client)

    out = screener_in_source.fetch(["ACGL"], aliases={"ACGL": "505036"})
    assert client.calls == [("505036", True), ("505036", False)]   # retried standalone
    assert out["ACGL"].market_cap == 1336.0
