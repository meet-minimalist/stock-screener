from __future__ import annotations

import logging

import pandas as pd

from screener.data.fetcher import DataFetcher
from screener.data.sectors import (
    MARKET_BENCHMARK,
    SECTOR_ETF,
    etf_for_sector,
    load_constituents,
    resolve_sector,
)

logger = logging.getLogger(__name__)

# Trailing-return windows in approximate trading days.
_RETURN_WINDOWS = {"ret_1m": 21, "ret_3m": 63, "ret_6m": 126, "ret_12m": 252}

# RRG quadrant -> where the sector sits in the rotation cycle.
# The cycle turns clockwise: Improving -> Leading -> Weakening -> Lagging.
QUADRANT_PHASE = {
    "Leading": "Outperforming & strengthening (bullish)",
    "Weakening": "Outperforming but losing momentum (take profits)",
    "Lagging": "Underperforming & weak (avoid)",
    "Improving": "Underperforming but gaining momentum (early accumulation)",
}


def _return_pct(close: pd.Series, days: int) -> float | None:
    """Return over the last ``days`` bars, in percent, or None if too short."""
    s = close.dropna()
    if len(s) <= days:
        return None
    base = float(s.iloc[-days - 1])
    if base <= 0:
        return None
    return (float(s.iloc[-1]) / base - 1.0) * 100.0


def classify_quadrant(rs_ratio: float | None, rs_momentum: float | None) -> str:
    """Map an (RS-Ratio, RS-Momentum) pair to its RRG quadrant (100 = neutral)."""
    if rs_ratio is None or rs_momentum is None:
        return "n/a"
    if rs_ratio >= 100 and rs_momentum >= 100:
        return "Leading"
    if rs_ratio >= 100 and rs_momentum < 100:
        return "Weakening"
    if rs_ratio < 100 and rs_momentum < 100:
        return "Lagging"
    return "Improving"


def _rrg_frame(
    sector_close: pd.Series, bench_close: pd.Series, window: int = 63
) -> pd.DataFrame:
    """RS-Ratio / RS-Momentum time series for one sector vs the benchmark.

    RS       = sector / benchmark (relative strength line)
    RS-Ratio = 100 * RS / SMA(RS, window)          -> RS vs its own trend
    RS-Mom   = 100 * Ratio / SMA(Ratio, window)     -> rate of change of the ratio

    >100 means "above trend". The (Ratio, Momentum) pair at any date lands in one
    of four quadrants describing the sector's rotation phase. This is a
    transparent approximation of the proprietary RRG normalisation, good enough
    to classify and rank sectors consistently. Returns an empty frame when there
    is not enough overlapping history.
    """
    idx = sector_close.dropna().index.intersection(bench_close.dropna().index)
    if len(idx) < window + 2:
        return pd.DataFrame(columns=["rs_ratio", "rs_momentum"])

    rs = (sector_close.loc[idx] / bench_close.loc[idx]) * 100.0
    ratio = 100.0 * rs / rs.rolling(window).mean()
    momentum = 100.0 * ratio / ratio.rolling(window).mean()
    return pd.DataFrame({"rs_ratio": ratio, "rs_momentum": momentum}).dropna()


def _rrg_quadrant(
    sector_close: pd.Series, bench_close: pd.Series, window: int = 63
) -> dict:
    """Latest RS-Ratio, RS-Momentum, and quadrant for one sector vs the market."""
    frame = _rrg_frame(sector_close, bench_close, window)
    if frame.empty:
        return {"rs_ratio": None, "rs_momentum": None, "quadrant": "n/a"}
    rv = float(frame["rs_ratio"].iloc[-1])
    mv = float(frame["rs_momentum"].iloc[-1])
    return {"rs_ratio": round(rv, 2), "rs_momentum": round(mv, 2),
            "quadrant": classify_quadrant(rv, mv)}


def compute_rrg_tails(
    start_date: str,
    end_date: str,
    interval: str = "1d",
    rrg_window: int = 63,
    tail_weeks: int = 12,
    cache_dir: str = "data/yfinance_cache",
) -> dict[str, pd.DataFrame]:
    """RS-Ratio/Momentum trajectory ("tail") for every sector, for an RRG plot.

    Each sector's series is sampled weekly (to cut daily noise) and trimmed to
    the last ``tail_weeks`` points. The final row is "now"; earlier rows show
    where the sector was over the preceding weeks (~12 weeks = 3 months,
    ~26 = 6 months). Returns ``{sector: DataFrame[rs_ratio, rs_momentum, ...]}``.
    """
    fetcher = DataFetcher(cache_dir=cache_dir)
    bench = fetcher.get_data(MARKET_BENCHMARK, start_date, end_date, interval=interval)
    if bench.empty:
        raise RuntimeError(f"No data for market benchmark {MARKET_BENCHMARK}")
    bench_close = bench["Close"]

    tails: dict[str, pd.DataFrame] = {}
    for sector, etf in SECTOR_ETF.items():
        df = fetcher.get_data(etf, start_date, end_date, interval=interval)
        if df.empty:
            continue
        frame = _rrg_frame(df["Close"], bench_close, window=rrg_window)
        if frame.empty:
            continue
        if isinstance(frame.index, pd.DatetimeIndex):
            frame = frame.resample("W-FRI").last().dropna()
        tail = frame.tail(tail_weeks).copy()
        if tail.empty:
            continue
        tail["sector"] = sector
        tail["etf"] = etf
        tails[sector] = tail
    return tails


def compute_sector_rotation(
    start_date: str,
    end_date: str,
    interval: str = "1d",
    rrg_window: int = 63,
    cache_dir: str = "data/yfinance_cache",
) -> pd.DataFrame:
    """Build a sector-rotation table: one row per sector ETF vs the market.

    Columns: sector, etf, last_price, RRG quadrant + phase, RS ratio/momentum,
    trailing returns, and each return relative to the market benchmark.
    Sorted by 3-month relative return, strongest first.
    """
    fetcher = DataFetcher(cache_dir=cache_dir)

    bench = fetcher.get_data(MARKET_BENCHMARK, start_date, end_date, interval=interval)
    if bench.empty:
        raise RuntimeError(f"No data for market benchmark {MARKET_BENCHMARK}")
    bench_close = bench["Close"]
    bench_ret = {k: _return_pct(bench_close, d) for k, d in _RETURN_WINDOWS.items()}

    rows: list[dict] = []
    for sector, etf in SECTOR_ETF.items():
        df = fetcher.get_data(etf, start_date, end_date, interval=interval)
        if df.empty:
            logger.warning("No data for %s (%s)", sector, etf)
            continue
        close = df["Close"]
        rrg = _rrg_quadrant(close, bench_close, window=rrg_window)

        row = {
            "sector": sector,
            "etf": etf,
            "last_price": round(float(close.iloc[-1]), 2),
            "quadrant": rrg["quadrant"],
            "phase": QUADRANT_PHASE.get(rrg["quadrant"], ""),
            "rs_ratio": rrg["rs_ratio"],
            "rs_momentum": rrg["rs_momentum"],
        }
        for key, days in _RETURN_WINDOWS.items():
            sr = _return_pct(close, days)
            row[key] = round(sr, 1) if sr is not None else None
            br = bench_ret[key]
            rel = key.replace("ret_", "rel_")
            row[rel] = round(sr - br, 1) if (sr is not None and br is not None) else None
        rows.append(row)

    out = pd.DataFrame(rows)
    if not out.empty and "rel_3m" in out.columns:
        out = out.sort_values("rel_3m", ascending=False, na_position="last").reset_index(drop=True)
    return out


def compare_sector_peers(
    sector: str,
    start_date: str,
    end_date: str,
    interval: str = "1d",
    window_days: int = 63,
    cache_dir: str = "data/yfinance_cache",
    max_names: int | None = None,
) -> pd.DataFrame:
    """Rank the stocks in one sector against each other and the sector ETF.

    ``window_days`` sets the comparison horizon (default ~3 months / 63 bars).
    ``rel_return`` = stock return minus the sector ETF return over that window;
    positive means the stock is beating its own sector. Sorted best-to-worst.
    """
    canonical = resolve_sector(sector)
    etf = etf_for_sector(canonical)
    fetcher = DataFetcher(cache_dir=cache_dir)

    etf_df = fetcher.get_data(etf, start_date, end_date, interval=interval)
    if etf_df.empty:
        raise RuntimeError(f"No data for sector ETF {etf}")
    sector_ret = _return_pct(etf_df["Close"], window_days)
    bench_df = fetcher.get_data(MARKET_BENCHMARK, start_date, end_date, interval=interval)
    market_ret = _return_pct(bench_df["Close"], window_days) if not bench_df.empty else None

    constituents = load_constituents(canonical)
    symbols = constituents["Symbol"].tolist()
    if max_names is not None:
        symbols = symbols[:max_names]
    name_map = dict(zip(constituents["Symbol"], constituents["Security"]))

    rows: list[dict] = []
    for sym in symbols:
        df = fetcher.get_data(sym, start_date, end_date, interval=interval)
        if df.empty:
            continue
        ret = _return_pct(df["Close"], window_days)
        if ret is None:
            continue
        rows.append(
            {
                "ticker": sym,
                "name": name_map.get(sym, ""),
                "last_price": round(float(df["Close"].iloc[-1]), 2),
                "return": round(ret, 1),
                "rel_sector": round(ret - sector_ret, 1) if sector_ret is not None else None,
                "rel_market": round(ret - market_ret, 1) if market_ret is not None else None,
                "beats_sector": (sector_ret is not None and ret > sector_ret),
            }
        )

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("return", ascending=False, na_position="last").reset_index(drop=True)
        out.attrs["sector"] = canonical
        out.attrs["etf"] = etf
        out.attrs["sector_return"] = sector_ret
        out.attrs["market_return"] = market_ret
        out.attrs["window_days"] = window_days
    return out
