from __future__ import annotations

import logging
import os
import shutil
import time

import pandas as pd
from yf_cache import YFinanceDataDownloader

logger = logging.getLogger(__name__)

# Retries and backoff are env-tunable so CI can dial them without a code change.
_DEFAULT_RETRIES = int(os.getenv("YF_FETCH_RETRIES", "2"))
_BACKOFF_BASE = float(os.getenv("YF_FETCH_BACKOFF", "0.5"))


def _sleep(seconds: float) -> None:
    # Wrapped so tests can monkeypatch out the backoff.
    time.sleep(seconds)


def _clean(df: pd.DataFrame | None) -> pd.DataFrame:
    """Drop rows with no Close.

    yfinance often returns a trailing bar whose Close is NaN (an unsettled/holiday
    day). Left in, that NaN becomes the record's ``price`` -- the source of the many
    ``price: NaN`` cells on the page. Removing NaN-Close rows makes the latest *valid*
    bar the price. If every row is NaN the frame becomes empty and the name is treated
    as an empty fetch (below), which is correct.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    return df[df["Close"].notna()]


class DataFetcher:
    def __init__(self, cache_dir: str = "data/yfinance_cache",
                 retries: int | None = None):
        self._cache_dir = cache_dir
        self._downloader = YFinanceDataDownloader(cache_dir=cache_dir)
        self._retries = _DEFAULT_RETRIES if retries is None else retries

    def _attempt(self, ticker: str, start_date: str, end_date: str,
                 interval: str) -> pd.DataFrame:
        try:
            return _clean(self._downloader.get_data(
                ticker, start_date, end_date, interval=interval))
        except Exception as exc:  # noqa: BLE001 - network/parse errors are non-fatal
            logger.warning("Failed to fetch data for %s: %s", ticker, exc)
            return pd.DataFrame()

    def get_data(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        df = self._attempt(ticker, start_date, end_date, interval)
        if not df.empty:
            return df

        # Empty result. Only a broken *cached* entry is worth healing: yf_cache reloads
        # an existing-but-empty month forever (this is how a fresh 52w-high breakout like
        # FLUOROCHEM silently vanished from every build), so purge and re-fetch live. A
        # symbol with no cache at all is either brand-new or -- far more often -- a
        # dead/unlisted ticker (e.g. MCCHRLS-B.NS); retrying it only multiplies Yahoo's
        # per-month "data doesn't exist" errors, so leave it alone.
        tdir = os.path.join(self._cache_dir, ticker)
        if not os.path.isdir(tdir):
            return df
        shutil.rmtree(tdir, ignore_errors=True)
        logger.info("Purged stale/empty cache for %s; forcing live re-fetch", ticker)

        for attempt in range(self._retries):
            _sleep(_BACKOFF_BASE * (2 ** attempt))
            df = self._attempt(ticker, start_date, end_date, interval)
            if not df.empty:
                logger.info("Recovered %s on retry %d/%d", ticker, attempt + 1,
                            self._retries)
                return df

        logger.debug("No data for %s after %d attempt(s)", ticker, self._retries + 1)
        return df
