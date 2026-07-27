from __future__ import annotations

import pandas as pd

from screener.data import bse


def _bse_rows():
    """A synthetic BSE ListofScripData frame covering every filter branch."""
    cols = ["SCRIP_CD", "Scrip_Name", "GROUP", "ISIN_NUMBER", "INDUSTRY", "scrip_id", "Mktcap"]
    rows = [
        # Real BSE-exclusive mainboard company -> kept.
        ["544467", "National Securities Depository Ltd", "A", "INE192801020", "Financials", "NSDL", "16356.0"],
        # Also exclusive, group B -> kept.
        ["505036", "Automobile Corporation of Goa Ltd", "B", "INE451C01013", None, "ACGL", "1336.15"],
        # Low-liquidity group X but above the floor -> kept.
        ["511644", "Omega Interactive Technologies Ltd", "X", "INE113B01037", None, "OMEGAIN", "394.97"],
        # ISIN is on NSE -> not exclusive, dropped.
        ["500325", "Reliance Industries Ltd", "A", "INE002A01018", None, "RELIANCE", "1900000.0"],
        # Mutual-fund unit (INF ISIN) -> dropped.
        ["990001", "Some Savings Fund Direct Growth", "B", "INF204KB14I5", None, "08ABB", ""],
        # Group X but below the market-cap floor -> dropped.
        ["512345", "Tiny Penny Shell Ltd", "X", "INE999X01019", None, "TINYPNY", "12.0"],
        # ETF by name -> dropped.
        ["590115", "Motilal Oswal Nifty 50 ETF", "B", "INE732G01029", None, "MOM50", "1289.0"],
        # SME-platform group (M) -> dropped even above the floor.
        ["543210", "Some SME Co Ltd", "M", "INE555M01011", None, "SMECO", "600.0"],
        # Duplicate ISIN of NSDL, smaller cap -> deduped away (keep the larger cap).
        ["544468", "NSDL Duplicate Line", "B", "INE192801020", None, "NSDLDUP", "5.0"],
    ]
    return pd.DataFrame(rows, columns=cols)


def test_bse_only_keeps_exclusive_mainboard_companies_only():
    out = bse._bse_only(_bse_rows(), nse_isins={"INE002A01018"})
    kept = set(out["Symbol"])
    assert kept == {"NSDL", "ACGL", "OMEGAIN"}            # exclusive A/B/X above the floor
    assert "RELIANCE" not in kept                         # on NSE
    assert "08ABB" not in kept                            # INF mutual-fund unit
    assert "TINYPNY" not in kept                          # below the market-cap floor
    assert "MOM50" not in kept                            # ETF
    assert "SMECO" not in kept                            # SME platform (group not kept)


def test_bse_only_columns_and_yf_symbol():
    out = bse._bse_only(_bse_rows(), nse_isins=set())
    assert list(out.columns) == bse._COLUMNS
    nsdl = out.set_index("Symbol").loc["NSDL"]
    assert nsdl["ScripCode"] == "544467"                  # screener.in slug is the code
    assert nsdl["YF"] == "NSDL.BO"                        # yfinance / yf_cache symbol
    assert nsdl["ISIN Code"] == "INE192801020"


def test_bse_only_dedupes_shared_isin_keeping_largest_cap():
    out = bse._bse_only(_bse_rows(), nse_isins=set())
    assert (out["ISIN Code"] == "INE192801020").sum() == 1
    assert "NSDLDUP" not in set(out["Symbol"])            # smaller-cap clone dropped


def test_market_cap_floor_trims_the_penny_tail():
    # Default floor drops the sub-floor shell; dropping it lets the penny name back.
    assert "TINYPNY" not in set(bse._bse_only(_bse_rows(), nse_isins=set())["Symbol"])
    out = bse._bse_only(_bse_rows(), nse_isins=set(), min_mktcap=0.0)
    assert "TINYPNY" in set(out["Symbol"])


def test_group_filter_is_configurable():
    # Narrowing to A/B only drops the low-liquidity X name (Omega Interactive).
    out = bse._bse_only(_bse_rows(), nse_isins=set(), groups=("A", "B"))
    assert "OMEGAIN" not in set(out["Symbol"])
    assert {"NSDL", "ACGL"} <= set(out["Symbol"])


def test_india_extra_universe_maps_ticker_slug_and_sector(monkeypatch):
    frame = pd.DataFrame({
        "Symbol": ["NSDL", "ACGL"],
        "ScripCode": ["544467", "505036"],
        "Company Name": ["National Securities Depository Ltd", "Automobile Corp of Goa Ltd"],
        "Industry": ["Financials", None],
        "ISIN Code": ["INE192801020", "INE451C01013"],
        "Group": ["A", "B"],
        "MktCap": [16356.0, 1336.15],
        "YF": ["NSDL.BO", "ACGL.BO"],
    })
    monkeypatch.setattr(bse, "load_bse_only", lambda: frame)
    tickers, aliases, sectors = bse.india_extra_universe()
    assert tickers == ["NSDL", "ACGL"]
    assert aliases == {"NSDL": "544467", "ACGL": "505036"}  # display ticker -> screener.in slug
    assert sectors == {"NSDL": "Financials", "ACGL": None}  # blank industry -> None


def test_india_extra_universe_empty_when_no_list(monkeypatch):
    monkeypatch.setattr(bse, "load_bse_only", lambda: pd.DataFrame(columns=bse._COLUMNS))
    assert bse.india_extra_universe() == ([], {}, {})
