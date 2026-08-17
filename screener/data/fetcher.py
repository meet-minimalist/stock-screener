from __future__ import annotations

import logging
import os
import shutil
import time

import pandas as pd
from yf_cache import YFinanceDataDownloader

logger = logging.getLogger(__name__)

# Retries/backoff for plain empty results (broken cache). Env-tunable.
_DEFAULT_RETRIES = int(os.getenv("YF_FETCH_RETRIES", "2"))
_BACKOFF_BASE = float(os.getenv("YF_FETCH_BACKOFF", "0.5"))
# Rate-limit backoff: when Yahoo 429s, wait (escalating, capped) and retry the ticker.
_RL_RETRIES = int(os.getenv("YF_RL_RETRIES", "3"))
_RL_BASE = float(os.getenv("YF_RL_BACKOFF", "5"))
_RL_CAP = float(os.getenv("YF_RL_BACKOFF_CAP", "30"))
# How many trailing months to re-download. yf_cache never refreshes a month whose file
# already exists, so the current (incomplete) month would otherwise go stale. Refreshing
# just the current month (daily runs keep the previous one complete) makes ~1 request per
# ticker, not a full re-download. Guarded by mtime below so rapid rebuilds don't re-pull a
# month that was just fetched -- which is what would otherwise pile onto Yahoo's rate limit.
_REFRESH_RECENT_MONTHS = int(os.getenv("YF_REFRESH_RECENT_MONTHS", "1"))
# Don't re-pull a month whose cache file was written within this window (seconds): it is
# already fresh, so a same-hour rebuild adds no load.
_REFRESH_MIN_AGE = float(os.getenv("YF_REFRESH_MIN_AGE", "21600"))  # 6h

# Incremented by the log tap below whenever yf_cache reports a Yahoo rate limit. The
# fetcher reads its delta to tell a throttled fetch apart from a genuinely-empty one.
rate_limit_hits = 0


class _YFCacheLogTap(logging.Filter):
    """Tame yf_cache.downloader noise and count rate-limit events.

    - "Data doesn't exist" (pre-listing months of a new listing): dropped.
    - "Too Many Requests"/"Rate limited": counted so the fetcher can back off, and the
      noisy per-month line is muted -- one concise notice comes from the fetcher instead.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        global rate_limit_hits
        msg = record.getMessage()
        if "Rate limited" in msg or "Too Many Requests" in msg:
            rate_limit_hits += 1
            return False
        if "Data doesn't exist" in msg:
            return False
        return True


logging.getLogger("yf_cache.downloader").addFilter(_YFCacheLogTap())


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
                 retries: int | None = None, rl_retries: int | None = None,
                 refresh_recent: int | None = None):
        self._cache_dir = cache_dir
        self._downloader = YFinanceDataDownloader(cache_dir=cache_dir)
        self._retries = _DEFAULT_RETRIES if retries is None else retries
        self._rl_retries = _RL_RETRIES if rl_retries is None else rl_retries
        self._refresh_recent = _REFRESH_RECENT_MONTHS if refresh_recent is None else refresh_recent

    def _ticker_dir(self, ticker: str) -> str:
        return os.path.join(self._cache_dir, ticker.upper())

    def _refresh_recent_months(self, ticker: str, end_date: str, interval: str) -> None:
        """Delete the cache file(s) for the last ``_refresh_recent`` months so yf_cache
        re-downloads them fresh (it never refreshes a month whose file already exists).

        A file written within ``_REFRESH_MIN_AGE`` is left alone -- it's already fresh, so
        a rapid rebuild adds no requests and can't pile onto Yahoo's rate limit."""
        if self._refresh_recent <= 0:
            return
        try:
            y, m = (int(p) for p in str(end_date)[:7].split("-"))
        except ValueError:
            return
        base = os.path.join(self._ticker_dir(ticker), interval)
        now = time.time()
        for _ in range(self._refresh_recent):
            p = os.path.join(base, f"{y:04d}-{m:02d}.csv")
            if os.path.exists(p):
                try:
                    if now - os.path.getmtime(p) >= _REFRESH_MIN_AGE:
                        os.remove(p)
                except OSError:
                    pass
            m -= 1
            if m == 0:
                y, m = y - 1, 12

    def _attempt(self, ticker: str, start_date: str, end_date: str,
                 interval: str) -> tuple[pd.DataFrame, bool]:
        """One fetch. Returns (frame, was_rate_limited)."""
        before = rate_limit_hits
        try:
            df = _clean(self._downloader.get_data(
                ticker, start_date, end_date, interval=interval))
        except Exception as exc:  # noqa: BLE001 - network/parse errors are non-fatal
            logger.warning("Failed to fetch data for %s: %s", ticker, exc)
            df = pd.DataFrame()
        return df, (rate_limit_hits > before)

    def get_data(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        # Always re-pull the trailing month(s) so today's bars aren't frozen in a stale
        # cached month; old history stays cached, so this is ~2 requests, not a full one.
        self._refresh_recent_months(ticker, end_date, interval)
        df, limited = self._attempt(ticker, start_date, end_date, interval)
        if not df.empty:
            return df

        # Rate limited: Yahoo throttled this fetch (a cold-cache full re-download is the
        # usual trigger). yf_cache does NOT cache the failed months, so waiting for the
        # limit to reset and retrying the whole ticker recovers its data -- and the
        # escalating backoff paces the run so the throttling subsides.
        n = 0
        while df.empty and limited and n < self._rl_retries:
            wait = min(_RL_BASE * (2 ** n), _RL_CAP)
            logger.warning("Rate limited on %s; backing off %.0fs (retry %d/%d)",
                           ticker, wait, n + 1, self._rl_retries)
            _sleep(wait)
            df, limited = self._attempt(ticker, start_date, end_date, interval)
            n += 1
        if not df.empty:
            return df

        # Still empty and not (any longer) rate limited. Only a broken *cached* entry is
        # worth healing: yf_cache reloads an existing-but-empty month forever (this is how
        # FLUOROCHEM silently vanished), so purge and re-fetch. A symbol with no cache is
        # brand-new or -- more often -- dead/unlisted; retrying it just wastes calls.
        tdir = self._ticker_dir(ticker)
        if not os.path.isdir(tdir):
            return df
        shutil.rmtree(tdir, ignore_errors=True)
        logger.info("Purged stale/empty cache for %s; forcing live re-fetch", ticker)

        for attempt in range(self._retries):
            _sleep(_BACKOFF_BASE * (2 ** attempt))
            df, _ = self._attempt(ticker, start_date, end_date, interval)
            if not df.empty:
                logger.info("Recovered %s on retry %d/%d", ticker, attempt + 1,
                            self._retries)
                return df

        logger.debug("No data for %s after retries", ticker)
        return df
