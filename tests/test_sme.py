from __future__ import annotations

import pandas as pd

from screener.data import sme


def _nse_raw():
    return pd.DataFrame({
        "SYMBOL": ["METALIC", "ANAWIL", "SUSPENDED"],
        "NAME_OF_COMPANY": ["Metalic Technoforge Ltd", "Anawil Wire Ltd", "Dead Co Ltd"],
        "SERIES": ["SM", "ST", "SZ"],                      # SZ (suspended) dropped
        "ISIN_NUMBER": ["INE001A01011", "INE002B01022", "INE003C01033"],
    })


def _bse_raw():
    return pd.DataFrame({
        "SCRIP_CD": ["543001", "543002", "500325"],
        "Scrip_Name": ["Bothra Metals Ltd", "Shared ISIN Co Ltd", "Reliance (mainboard)"],
        "scrip_id": ["BMAL", "DUPES", "RELIANCE"],
        "GROUP": ["M", "MT", "A"],                          # A is mainboard, dropped
        "ISIN_NUMBER": ["INE111X01019", "INE001A01011", "INE002A01018"],
    })


def test_build_unions_both_platforms_and_drops_non_sme():
    out = sme._build(_nse_raw(), _bse_raw())
    kept = set(out["Symbol"])
    assert {"METALIC", "ANAWIL", "BMAL"} <= kept
    assert "SUSPENDED" not in kept        # SZ series dropped
    assert "RELIANCE" not in kept         # BSE group A is mainboard, not SME


def test_build_dedupes_shared_isin_preferring_nse():
    # METALIC (NSE) and DUPES (BSE) share INE001A01011 -> NSE kept, BSE dropped.
    out = sme._build(_nse_raw(), _bse_raw())
    assert (out["ISIN Code"] == "INE001A01011").sum() == 1
    row = out.set_index("ISIN Code").loc["INE001A01011"]
    assert row["Symbol"] == "METALIC" and row["Exchange"] == "NSE"
    assert "DUPES" not in set(out["Symbol"])


def test_yf_symbols_use_ns_for_nse_and_bo_for_bse():
    out = sme._build(_nse_raw(), _bse_raw()).set_index("Symbol")
    assert out.loc["METALIC", "YF"] == "METALIC.NS"
    assert out.loc["BMAL", "YF"] == "BMAL.BO"


def test_price_and_fundamentals_universes(monkeypatch):
    frame = sme._build(_nse_raw(), _bse_raw())
    monkeypatch.setattr(sme, "load_sme", lambda refresh=False: frame)

    tickers, sectors, price = sme.sme_price_universe()
    assert price["METALIC"] == "METALIC.NS" and price["BMAL"] == "BMAL.BO"

    _t, aliases, _sec = sme.sme_universe()
    assert aliases["BMAL"] == "543001"    # BSE SME -> screener.in numeric scrip code
    assert "METALIC" not in aliases       # NSE resolves by its own symbol


def test_in_sme_has_a_fundamentals_source_registered():
    # Regression: refresh_market("in_sme") must resolve to the screener.in source.
    from screener.fundamentals import service
    assert "in_sme" in service._SOURCES
    assert service._SOURCES["in_sme"] is service._SOURCES["in"]


def test_run_daily_sme_prices_names_by_their_own_yf_symbols(monkeypatch):
    """SME market must price NSE Emerge via .NS and BSE SME via .BO, from the SME map."""
    import screener.daily_report as dr

    fetched: list[str] = []

    class FakeFetcher:
        def __init__(self, cache_dir=None):
            pass

        def get_data(self, symbol, *a, **k):
            fetched.append(symbol)
            return pd.DataFrame()          # empty -> light; we only assert routing

    monkeypatch.setattr(dr, "DataFetcher", FakeFetcher)
    monkeypatch.setattr(dr, "compute_sector_rotation", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(dr, "get_ticker_list", lambda u: ["METALIC", "BMAL"])
    monkeypatch.setattr(dr, "load_constituents", lambda market="us": pd.DataFrame(
        {"Symbol": ["METALIC", "BMAL"], "sector": [None, None]}))
    monkeypatch.setattr(dr, "get_fundamentals", lambda m, t: {})
    monkeypatch.setattr("screener.data.sme.sme_price_universe",
                        lambda: (["METALIC", "BMAL"], {},
                                 {"METALIC": "METALIC.NS", "BMAL": "BMAL.BO"}))

    dr.run_daily("2025-01-01", "2026-01-01", universe="india_sme",
                 market="in_sme", show_progress=False)
    assert "METALIC.NS" in fetched and "BMAL.BO" in fetched
