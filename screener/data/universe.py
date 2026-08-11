from __future__ import annotations

import logging
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from screener.paths import TICKERS_DIR

logger = logging.getLogger(__name__)

CACHE_DIR = TICKERS_DIR

# Each S&P index has an identically-shaped Wikipedia constituents table
# (Symbol, Security, GICS Sector, ...). sp1500 is the union of the three tiers.
_INDEX_SOURCES = {
    "sp500": ("sp500.csv", "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"),
    "sp400": ("sp400.csv", "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"),
    "sp600": ("sp600.csv", "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"),
}
SP1500_TIERS = ("sp500", "sp400", "sp600")

# NSE publishes index constituents as direct CSVs (Company Name, Industry,
# Symbol, Series, ISIN Code). Symbols are the bare NSE symbol (screener.in form);
# yfinance needs a ``.NS`` suffix, added at price-fetch time.
_NSE_SOURCES = {
    "nifty_total": ("nifty_total.csv",
                    "https://niftyindices.com/IndexConstituent/ind_niftytotalmarket_list.csv"),
    "nifty500": ("nifty500.csv",
                 "https://niftyindices.com/IndexConstituent/ind_nifty500list.csv"),
    "nifty_midsmallcap400": ("nifty_midsmallcap400.csv",
                             "https://niftyindices.com/IndexConstituent/ind_niftymidsmallcap400list.csv"),
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def _ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def fetch_index(key: str, force_refresh: bool = False) -> pd.DataFrame:
    """Fetch/cache one S&P index's constituents table (Symbol, Security, GICS Sector).

    Reads the committed/cached CSV when present; otherwise scrapes the Wikipedia
    table, normalises symbols to the ``.`` -> ``-`` convention, and caches it.
    """
    if key not in _INDEX_SOURCES:
        raise ValueError(f"Unknown index '{key}'. Known: {', '.join(_INDEX_SOURCES)}")
    _ensure_cache_dir()
    filename, url = _INDEX_SOURCES[key]
    cache = CACHE_DIR / filename
    if cache.exists() and not force_refresh:
        return pd.read_csv(cache)

    logger.info("Fetching %s constituents from Wikipedia...", key.upper())
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    df = pd.read_html(StringIO(resp.text))[0]
    df["Symbol"] = df["Symbol"].astype(str).str.replace(".", "-", regex=False).str.strip()
    df.to_csv(cache, index=False)
    logger.info("Cached %d %s tickers", len(df), key.upper())
    return df


def fetch_nse_index(key: str, force_refresh: bool = False) -> pd.DataFrame:
    """Fetch/cache one NSE index's constituents CSV (Company Name, Industry, Symbol)."""
    if key not in _NSE_SOURCES:
        raise ValueError(f"Unknown NSE index '{key}'. Known: {', '.join(_NSE_SOURCES)}")
    _ensure_cache_dir()
    filename, url = _NSE_SOURCES[key]
    cache = CACHE_DIR / filename
    if cache.exists() and not force_refresh:
        return pd.read_csv(cache)

    logger.info("Fetching %s constituents from NSE...", key)
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()
    df.to_csv(cache, index=False)
    logger.info("Cached %d %s tickers", len(df), key)
    return df


def _index_symbols(key: str, force_refresh: bool = False) -> list[str]:
    return sorted(fetch_index(key, force_refresh)["Symbol"].dropna().tolist())


def _nse_equity_symbols(force_refresh: bool = False,
                        series: tuple[str, ...] = ("EQ",)) -> list[str]:
    """Every NSE *mainboard* equity symbol from the full ``EQUITY_L`` list.

    Kept to the requested ``series`` — ``EQ`` (normal rolling settlement) by default,
    dropping the ``BE``/``BZ`` trade-for-trade and surveillance segments (the NSE
    analogue of the BSE T/Z groups). The list is fetched and cached by
    ``screener.data.bse`` (``nse_equity_full.csv``); we reuse that cache here rather
    than hitting NSE again. NSE Emerge SME names use a separate feed and are absent.
    """
    from screener.data.bse import NSE_EQUITY_CACHE, fetch_nse_isins
    if force_refresh or not NSE_EQUITY_CACHE.exists():
        fetch_nse_isins(force_refresh=True)          # side effect: writes the cache
    df = pd.read_csv(NSE_EQUITY_CACHE)
    df.columns = [c.strip() for c in df.columns]
    sym_col = next((c for c in df.columns if c.upper() == "SYMBOL"), "SYMBOL")
    ser_col = next((c for c in df.columns if c.upper() == "SERIES"), None)
    if ser_col is not None:
        df = df[df[ser_col].astype(str).str.strip().isin(series)]
    return df[sym_col].astype(str).str.strip().str.upper().tolist()


def fetch_sp500(force_refresh: bool = False) -> list[str]:
    """Back-compat helper: the S&P 500 symbol list."""
    return _index_symbols("sp500", force_refresh)


def get_ticker_list(source: str = "sp500", force_refresh: bool = False) -> list[str]:
    """Resolve a universe name to a sorted ticker list.

    Accepts ``sp500`` / ``sp400`` / ``sp600`` (single tier), ``sp1500`` (large +
    mid + small combined), or a path to a CSV of tickers.
    """
    source = source.lower()
    if source in _INDEX_SOURCES:
        return _index_symbols(source, force_refresh)
    if source in ("sp1500", "sp_1500"):
        symbols: set[str] = set()
        for tier in SP1500_TIERS:
            symbols.update(_index_symbols(tier, force_refresh))
        return sorted(symbols)
    if source == "india_sme":
        from screener.data.sme import load_sme
        return sorted(load_sme(force_refresh)["Symbol"].dropna().astype(str).tolist())
    if source in ("nse_all", "india_all"):
        # The whole investable NSE: full mainboard equity list unioned with the Nifty
        # Total Market index (a handful of index names sit in non-EQ series, so the
        # union never drops a current constituent).
        symbols = set(_nse_equity_symbols(force_refresh))
        symbols.update(fetch_nse_index("nifty_total", force_refresh)["Symbol"]
                       .dropna().astype(str).str.strip().str.upper())
        return sorted(symbols)
    if source in _NSE_SOURCES:
        return sorted(fetch_nse_index(source, force_refresh)["Symbol"].dropna().tolist())
    if source.endswith(".csv"):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Ticker file not found: {path}")
        df = pd.read_csv(path)
        col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        return sorted(df[col].dropna().astype(str).str.strip().tolist())
    raise ValueError(f"Unknown universe source: {source}")
