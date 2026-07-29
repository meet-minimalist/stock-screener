from __future__ import annotations

import pandas as pd

from screener.data import universe
from screener.data.bse import NSE_EQUITY_CACHE
from screener.data.universe import get_ticker_list


def _series_symbol(series: str) -> str | None:
    """A symbol from the cached NSE list trading in the given series, if any."""
    df = pd.read_csv(NSE_EQUITY_CACHE)
    df.columns = [c.strip() for c in df.columns]
    hit = df[df["SERIES"].astype(str).str.strip() == series]
    return None if hit.empty else str(hit.iloc[0]["SYMBOL"]).strip().upper()


def test_nse_all_unions_full_equity_with_the_index():
    syms = set(get_ticker_list("nse_all"))
    assert len(syms) > 2000                          # far wider than the 751-name index
    assert "JASH" in syms                            # the name that prompted this
    assert "RELIANCE" in syms                        # a Nifty Total large cap
    # It is a superset of the Nifty Total Market index (the union guarantee).
    index_names = set(get_ticker_list("nifty_total"))
    assert index_names <= syms


def test_nse_all_keeps_eq_series_only():
    be = _series_symbol("BE")
    if be is not None:                               # BE/BZ surveillance names are dropped
        assert be not in set(universe._nse_equity_symbols())
