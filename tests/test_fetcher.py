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


def test_retries_recover_after_transient_empty(monkeypatch):
    monkeypatch.setattr(fetcher_mod, "YFinanceDataDownloader", _FakeDownloader)
    f = _fetcher(monkeypatch, [pd.DataFrame(), _frame([1.0, 2.0])])
    out = f.get_data("AAA", "2026-01-01", "2026-02-01")
    assert not out.empty and f._downloader.calls == 2


def test_gives_up_and_returns_empty_after_retries(monkeypatch):
    monkeypatch.setattr(fetcher_mod, "YFinanceDataDownloader", _FakeDownloader)
    f = _fetcher(monkeypatch, [pd.DataFrame()], retries=2)
    out = f.get_data("AAA", "2026-01-01", "2026-02-01")
    assert out.empty
    assert f._downloader.calls == 3               # 1 initial + 2 retries


def test_empty_purges_broken_cache_then_refetches(monkeypatch, tmp_path):
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


def test_empty_fetch_rate():
    from screener.daily_report import empty_fetch_rate
    assert empty_fetch_rate({"scanned": 100, "empty_fetches": 15}) == 0.15
    assert empty_fetch_rate({"scanned": 0, "empty_fetches": 0}) == 0.0
    assert empty_fetch_rate({"scanned": 10}) == 0.0        # key absent -> 0


def test_exception_is_swallowed_and_retried(monkeypatch):
    class _Boom(_FakeDownloader):
        def get_data(self, *a, **k):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("rate limited")
            return _frame([9.0])

    monkeypatch.setattr(fetcher_mod, "YFinanceDataDownloader", _Boom)
    monkeypatch.setattr(fetcher_mod, "_sleep", lambda *_: None)
    f = DataFetcher(cache_dir="nope", retries=2)
    out = f.get_data("AAA", "2026-01-01", "2026-02-01")
    assert not out.empty and f._downloader.calls == 2
