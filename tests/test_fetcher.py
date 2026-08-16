from __future__ import annotations

import numpy as np
import pandas as pd

from screener.data import fetcher as fetcher_mod
from screener.data.fetcher import DataFetcher, _clean


def _frame(closes):
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"Close": closes, "Volume": [1] * len(closes)}, index=idx)


def test_clean_drops_trailing_nan_close():
    df = _frame([10.0, 11.0, np.nan])
    out = _clean(df)
    assert len(out) == 2
    assert out["Close"].iloc[-1] == 11.0          # last VALID bar becomes the price


def test_clean_all_nan_close_becomes_empty():
    assert _clean(_frame([np.nan, np.nan])).empty


class _FakeDownloader:
    """Stand-in for yf_cache: yields a scripted sequence of frames per call."""

    def __init__(self, cache_dir=None):
        self.calls = 0
        self.sequence: list[pd.DataFrame] = []

    def get_data(self, ticker, start, end, interval="1d"):
        i = min(self.calls, len(self.sequence) - 1)
        self.calls += 1
        return self.sequence[i]


def _fetcher(monkeypatch, sequence, retries=2, cache_dir="nope"):
    monkeypatch.setattr(fetcher_mod, "_sleep", lambda *_: None)   # no real backoff
    f = DataFetcher(cache_dir=cache_dir, retries=retries)
    f._downloader.sequence = sequence
    return f


def test_broken_cache_purged_then_refetched(monkeypatch, tmp_path):
    # A broken cached entry: the dir exists but the fetch is empty until purged.
    monkeypatch.setattr(fetcher_mod, "YFinanceDataDownloader", _FakeDownloader)
    tdir = tmp_path / "BROKEN.NS"
    tdir.mkdir()
    (tdir / "2026-08.csv").write_text("")          # poisoned cache file
    f = _fetcher(monkeypatch, [pd.DataFrame(), _frame([5.0, 6.0])],
                 cache_dir=str(tmp_path))
    out = f.get_data("BROKEN.NS", "2026-01-01", "2026-08-17")
    assert not out.empty
    assert not tdir.exists()                        # cache was purged to force re-fetch
    assert f._downloader.calls == 2                 # 1 initial + 1 recovering retry


def test_dead_symbol_without_cache_is_not_retried(monkeypatch, tmp_path):
    # No cache dir -> a dead/unlisted symbol; must NOT retry (that only spams Yahoo).
    monkeypatch.setattr(fetcher_mod, "YFinanceDataDownloader", _FakeDownloader)
    f = _fetcher(monkeypatch, [pd.DataFrame()], cache_dir=str(tmp_path))
    out = f.get_data("DEAD.NS", "2026-01-01", "2026-02-01")
    assert out.empty
    assert f._downloader.calls == 1                 # single attempt, no retries


def test_broken_cache_gives_up_after_retries(monkeypatch, tmp_path):
    monkeypatch.setattr(fetcher_mod, "YFinanceDataDownloader", _FakeDownloader)
    tdir = tmp_path / "BROKEN.NS"
    tdir.mkdir()
    (tdir / "2026-08.csv").write_text("")
    f = _fetcher(monkeypatch, [pd.DataFrame()], retries=2, cache_dir=str(tmp_path))
    out = f.get_data("BROKEN.NS", "2026-01-01", "2026-08-17")
    assert out.empty
    assert f._downloader.calls == 3                 # 1 initial + 2 retries
    assert not tdir.exists()


def test_empty_fetch_rate():
    from screener.daily_report import empty_fetch_rate
    assert empty_fetch_rate({"scanned": 100, "empty_fetches": 15}) == 0.15
    assert empty_fetch_rate({"scanned": 0, "empty_fetches": 0}) == 0.0
    assert empty_fetch_rate({"scanned": 10}) == 0.0        # key absent -> 0


def test_degraded_fetch_rate_counts_empty_and_stale():
    from screener.daily_report import degraded_fetch_rate
    # 10 empty + 15 stale of 100 = 25% degraded (empty rate alone would miss the stale).
    assert degraded_fetch_rate({"scanned": 100, "empty_fetches": 10, "stale_fetches": 15}) == 0.25
    assert degraded_fetch_rate({"scanned": 100, "empty_fetches": 0, "stale_fetches": 30}) == 0.30
    assert degraded_fetch_rate({"scanned": 0}) == 0.0


def test_log_tap_drops_noise_and_counts_rate_limits():
    import logging
    f = fetcher_mod._YFCacheLogTap()

    def rec(msg):
        return logging.LogRecord("yf_cache.downloader", logging.ERROR, __file__, 1, msg, None, None)

    before = fetcher_mod.rate_limit_hits
    assert f.filter(rec("MCCHRLS-B.NS: Data doesn't exist for startDate = 1")) is False
    assert f.filter(rec("Error downloading KPL.NS: Too Many Requests. Rate limited.")) is False
    assert fetcher_mod.rate_limit_hits == before + 1        # rate limit counted
    assert f.filter(rec("Saved KPL.NS to cache")) is True   # unrelated lines pass


def test_rate_limit_backs_off_then_recovers(monkeypatch):
    monkeypatch.setattr(fetcher_mod, "YFinanceDataDownloader", _FakeDownloader)
    monkeypatch.setattr(fetcher_mod, "_sleep", lambda *_: None)
    f = DataFetcher(cache_dir="nope", rl_retries=3)
    calls = {"n": 0}

    def dl(ticker, s, e, interval="1d"):
        calls["n"] += 1
        if calls["n"] == 1:
            fetcher_mod.rate_limit_hits += 1     # simulate a 429 the tap would count
            return pd.DataFrame()
        return _frame([10.0, 11.0])

    f._downloader.get_data = dl
    out = f.get_data("KPL.NS", "2025-01-01", "2026-01-01")
    assert not out.empty and calls["n"] == 2     # backed off once, then recovered


def test_rate_limit_gives_up_after_rl_retries(monkeypatch):
    monkeypatch.setattr(fetcher_mod, "YFinanceDataDownloader", _FakeDownloader)
    monkeypatch.setattr(fetcher_mod, "_sleep", lambda *_: None)
    f = DataFetcher(cache_dir="nope", rl_retries=2)

    def dl(ticker, s, e, interval="1d"):
        fetcher_mod.rate_limit_hits += 1         # always throttled
        return pd.DataFrame()

    f._downloader.get_data = dl
    out = f.get_data("KPL.NS", "2025-01-01", "2026-01-01")
    assert out.empty                             # no cache dir -> no further purge retry


def test_exception_is_swallowed_and_retried(monkeypatch, tmp_path):
    class _Boom(_FakeDownloader):
        def get_data(self, *a, **k):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("rate limited")   # must not propagate
            return _frame([9.0])

    monkeypatch.setattr(fetcher_mod, "YFinanceDataDownloader", _Boom)
    monkeypatch.setattr(fetcher_mod, "_sleep", lambda *_: None)
    (tmp_path / "AAA").mkdir()                        # broken cache -> retry path engages
    (tmp_path / "AAA" / "m.csv").write_text("")
    f = DataFetcher(cache_dir=str(tmp_path), retries=2)
    out = f.get_data("AAA", "2026-01-01", "2026-02-01")
    assert not out.empty and f._downloader.calls == 2
