from __future__ import annotations

from screener.fundamentals import store
from screener.fundamentals.finviz_source import _chunks, _resolve
from screener.fundamentals.schema import Fundamentals, to_float, to_pct


def test_resolve_maps_returned_ticker_to_requested():
    req = {"AAPL": "AAPL", "MSFT": "MSFT", "AA": "AA"}
    assert _resolve("AAPL", req) == "AAPL"      # direct (real finviz)
    assert _resolve("AAAPL", req) == "AAPL"     # sandbox doubled first char
    assert _resolve("MMSFT", req) == "MSFT"
    assert _resolve("AA", req) == "AA"           # real doubled ticker matches directly
    assert _resolve("ZZZZ", req) is None         # not something we asked for


def test_resolve_dedoubles_only_into_requested_set():
    # "A" was requested (not "AA"); returned "AA" must resolve to "A".
    assert _resolve("AA", {"A": "A"}) == "A"


def test_chunks_splits_evenly():
    assert list(_chunks([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_to_pct_normalises_strings_and_fractions():
    assert to_pct("13.90%") == 13.9        # string keeps printed magnitude
    assert to_pct(0.2133) == 21.33         # finviz fraction -> percent
    assert to_pct(-0.05) == -5.0
    assert to_pct("-") is None
    assert to_pct(float("nan")) is None
    assert to_pct(None) is None


def test_to_float_parses_numbers_percents_and_blanks():
    assert to_float("15.3%") == 15.3
    assert to_float("-2.81%") == -2.81
    assert to_float("1,234.5") == 1234.5
    assert to_float(26.98) == 26.98
    assert to_float("-") is None
    assert to_float("") is None
    assert to_float(None) is None
    assert to_float(float("nan")) is None
    assert to_float("N/A") is None


def test_fundamentals_row_roundtrip():
    f = Fundamentals(
        ticker="AAPL", as_of="2026-07-14", sector="Information Technology",
        market_cap=3.2e12, pe=30.1, peg=2.1, ps=8.0, pb=45.0, roe=150.0,
        roi=55.0, net_margin=25.0, eps_growth=12.5, sales_growth=8.0,
        debt_equity=1.5, dividend_yield=0.5,
    )
    back = Fundamentals.from_row(f.to_row())
    assert back == f


def test_from_row_coerces_strings_and_missing():
    row = {"ticker": "MSFT", "as_of": "2026-07-14", "sector": "",
           "pe": "35.2", "roe": "40.1%", "debt_equity": "-", "market_cap": "nan"}
    f = Fundamentals.from_row(row)
    assert f.ticker == "MSFT"
    assert f.sector is None          # blank -> None
    assert f.pe == 35.2
    assert f.roe == 40.1
    assert f.debt_equity is None     # '-' -> None
    assert f.market_cap is None      # 'nan' -> None


def test_store_snapshot_and_load(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "FUNDAMENTALS_DIR", tmp_path / "fundamentals")
    funds = {
        "AAPL": Fundamentals("AAPL", "2026-07-14", pe=30.1, roe=150.0),
        "MSFT": Fundamentals("MSFT", "2026-07-14", pe=35.0, roe=40.0),
    }
    dated = store.save_snapshot("us", funds, as_of="2026-07-14")
    assert dated.exists()
    assert (dated.parent / "latest.csv").exists()

    loaded = store.load_latest("us")
    assert set(loaded) == {"AAPL", "MSFT"}
    assert loaded["AAPL"].pe == 30.1
    assert loaded["MSFT"].roe == 40.0


def test_load_latest_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "FUNDAMENTALS_DIR", tmp_path / "nope")
    assert store.load_latest("us") == {}
