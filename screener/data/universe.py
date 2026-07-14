from __future__ import annotations

import logging
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/tickers")
SP500_CACHE = CACHE_DIR / "sp500.csv"
SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def _ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def fetch_sp500(force_refresh: bool = False) -> list[str]:
    _ensure_cache_dir()
    if SP500_CACHE.exists() and not force_refresh:
        df = pd.read_csv(SP500_CACHE)
        logger.info("Loaded %d S&P 500 tickers from cache", len(df))
        return sorted(df["Symbol"].tolist())

    logger.info("Fetching S&P 500 list from Wikipedia...")
    resp = requests.get(SP500_WIKI_URL, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(StringIO(resp.text))
    df = tables[0]
    tickers = sorted(df["Symbol"].str.replace(".", "-", regex=False).tolist())
    df.to_csv(SP500_CACHE, index=False)
    logger.info("Cached %d S&P 500 tickers", len(tickers))
    return tickers


def get_ticker_list(source: str = "sp500", force_refresh: bool = False) -> list[str]:
    source = source.lower()
    if source == "sp500":
        return fetch_sp500(force_refresh)
    elif source.endswith(".csv"):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Ticker file not found: {path}")
        df = pd.read_csv(path)
        col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        return sorted(df[col].dropna().str.strip().tolist())
    else:
        raise ValueError(f"Unknown universe source: {source}")
