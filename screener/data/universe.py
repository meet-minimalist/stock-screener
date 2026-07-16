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


def _index_symbols(key: str, force_refresh: bool = False) -> list[str]:
    return sorted(fetch_index(key, force_refresh)["Symbol"].dropna().tolist())


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
    if source.endswith(".csv"):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Ticker file not found: {path}")
        df = pd.read_csv(path)
        col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        return sorted(df[col].dropna().astype(str).str.strip().tolist())
    raise ValueError(f"Unknown universe source: {source}")
