from __future__ import annotations

import datetime as _dt
import logging

from screener.fundamentals.schema import Fundamentals, to_float, to_pct

logger = logging.getLogger(__name__)

# For each finviz screener view: schema field -> (column, parser). Ratios and
# absolutes use to_float; percentage metrics use to_pct so every % field lands
# on one scale. "Ticker" is the join key across views.
_VALUATION_MAP = {
    "market_cap": ("Market Cap", to_float),
    "pe": ("P/E", to_float),
    "forward_pe": ("Forward P/E", to_float),
    "peg": ("PEG", to_float),
    "ps": ("P/S", to_float),
    "pb": ("P/B", to_float),
    "pfcf": ("P/FCF", to_float),
    "eps_growth": ("EPS This Y", to_pct),
    "eps_growth_next_y": ("EPS Next Y", to_pct),
    "eps_growth_5y": ("EPS Next 5Y", to_pct),
    "eps_growth_past5y": ("EPS Past 5Y", to_pct),
    "sales_growth": ("Sales Past 5Y", to_pct),
}
_FINANCIAL_MAP = {
    "roe": ("ROE", to_pct),
    "roa": ("ROA", to_pct),
    "roi": ("ROIC", to_pct),
    "gross_margin": ("Gross M", to_pct),
    "oper_margin": ("Oper M", to_pct),
    "net_margin": ("Profit M", to_pct),
    "debt_equity": ("Debt/Eq", to_float),
    "lt_debt_equity": ("LTDebt/Eq", to_float),
    "current_ratio": ("Curr R", to_float),
    "quick_ratio": ("Quick R", to_float),
    "dividend_yield": ("Dividend", to_pct),
}
_OWNERSHIP_MAP = {
    "insider_own": ("Insider Own", to_pct),
    "inst_own": ("Inst Own", to_pct),
    "short_float": ("Short Float", to_pct),
}
_OVERVIEW_MAP = {
    "sector": ("Sector", str),
    "industry": ("Industry", str),
}


def _normalise(ticker: str) -> str:
    # Match the universe/yfinance convention (BRK.B -> BRK-B).
    return str(ticker).strip().upper().replace(".", "-")


def _rows_by_ticker(df) -> dict:
    return {_normalise(r["Ticker"]): r for _, r in df.iterrows()}


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _resolve(returned: str, requested: dict[str, str]) -> str | None:
    """Map a finviz-returned ticker back to a symbol we requested.

    Against real finviz the symbol matches directly. In a sandboxed/mock
    environment the first character can be doubled (AAPL -> AAAPL); we undo that
    only when the de-doubled symbol is one we actually asked for, so it stays
    unambiguous (a real doubled ticker like AA is matched directly first).
    """
    n = _normalise(returned)
    if n in requested:
        return n
    if len(n) > 1 and n[0] == n[1] and n[1:] in requested:
        return n[1:]
    return None


def _apply(kwargs: dict, row, mapping: dict) -> None:
    if row is None:
        return
    for field, (col, parse) in mapping.items():
        value = row.get(col)
        kwargs[field] = None if value is None else (
            parse(value) if parse is not str else
            (None if str(value).strip() in ("", "-", "nan") else str(value).strip())
        )


def _screener_classes() -> dict:
    from finvizfinance.screener.financial import Financial
    from finvizfinance.screener.overview import Overview
    from finvizfinance.screener.ownership import Ownership
    from finvizfinance.screener.valuation import Valuation
    return {"val": Valuation, "fin": Financial, "own": Ownership, "ovr": Overview}


def _views_by_index(index: str, limit: int | None, sleep_sec: float) -> dict:
    # finvizfinance's screener_view can't take limit=None (it does `limit -= size`),
    # so "all" is a ceiling above any single index's size.
    row_cap = 10000 if limit is None else limit
    views = {}
    for key, cls in _screener_classes().items():
        s = cls()
        s.set_filter(filters_dict={"Index": index})
        views[key] = _rows_by_ticker(
            s.screener_view(limit=row_cap, verbose=0, sleep_sec=sleep_sec))
    return views


def _views_by_tickers(tickers: list[str], sleep_sec: float, chunk_size: int) -> dict:
    # Query finviz by an explicit symbol list, chunked to keep the URL short, and
    # key every returned row back to *our* requested symbol.
    requested = {_normalise(t): t for t in tickers}
    views = {"val": {}, "fin": {}, "own": {}, "ovr": {}}
    classes = _screener_classes()
    for chunk in _chunks(list(requested), chunk_size):
        ticker_str = ",".join(chunk)
        for key, cls in classes.items():
            s = cls()
            s.set_filter(ticker=ticker_str)
            df = s.screener_view(verbose=0, sleep_sec=sleep_sec)
            for _, row in df.iterrows():
                resolved = _resolve(row["Ticker"], requested)
                if resolved is not None:
                    views[key][resolved] = row
    return views


def fetch(index: str = "S&P 500", tickers: list[str] | None = None,
          limit: int | None = None, sleep_sec: float = 1.0,
          chunk_size: int = 100) -> dict[str, Fundamentals]:
    """Pull fundamentals from finviz, merging four screener views per ticker.

    Two modes:
    - ``tickers`` given → query finviz by that explicit symbol list (chunked) and
      key results by *our* symbols. Robust to finviz's ticker formatting and the
      right base for arbitrary universes (any cap tier).
    - otherwise → pull a whole ``index`` (e.g. "S&P 500") in bulk.

    ``limit`` caps rows in index mode (handy for tests); ``sleep_sec`` paces requests.
    """
    as_of = _dt.date.today().isoformat()
    if tickers:
        views = _views_by_tickers(list(tickers), sleep_sec, chunk_size)
        source = f"{len(tickers)} tickers"
    else:
        views = _views_by_index(index, limit, sleep_sec)
        source = f"index={index}"

    out: dict[str, Fundamentals] = {}
    for ticker, vrow in views["val"].items():
        kwargs: dict = {"ticker": ticker, "as_of": as_of}
        _apply(kwargs, vrow, _VALUATION_MAP)
        _apply(kwargs, views["fin"].get(ticker), _FINANCIAL_MAP)
        _apply(kwargs, views["own"].get(ticker), _OWNERSHIP_MAP)
        _apply(kwargs, views["ovr"].get(ticker), _OVERVIEW_MAP)
        out[ticker] = Fundamentals(**kwargs)

    logger.info("Fetched finviz fundamentals for %d tickers (%s)", len(out), source)
    return out
