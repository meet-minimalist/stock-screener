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


def fetch(index: str = "S&P 500", limit: int | None = None,
          sleep_sec: float = 1.0) -> dict[str, Fundamentals]:
    """Pull fundamentals for an index in bulk from finviz.

    Merges finvizfinance's Valuation, Financial, Ownership, and Overview screener
    views (each paginated server-side) per ticker into the Fundamentals schema.
    ``limit`` caps rows (handy for tests); ``sleep_sec`` paces requests politely.
    """
    from finvizfinance.screener.financial import Financial
    from finvizfinance.screener.overview import Overview
    from finvizfinance.screener.ownership import Ownership
    from finvizfinance.screener.valuation import Valuation

    as_of = _dt.date.today().isoformat()
    filters = {"Index": index}

    def _view(cls):
        s = cls()
        s.set_filter(filters_dict=filters)
        return s.screener_view(limit=limit, verbose=0, sleep_sec=sleep_sec)

    df_val = _view(Valuation)
    fin = _rows_by_ticker(_view(Financial))
    own = _rows_by_ticker(_view(Ownership))
    ovr = _rows_by_ticker(_view(Overview))

    def _apply(kwargs, row, mapping):
        if row is None:
            return
        for field, (col, parse) in mapping.items():
            value = row.get(col)
            kwargs[field] = None if value is None else (
                parse(value) if parse is not str else
                (None if str(value).strip() in ("", "-", "nan") else str(value).strip())
            )

    out: dict[str, Fundamentals] = {}
    for _, vrow in df_val.iterrows():
        ticker = _normalise(vrow["Ticker"])
        kwargs: dict = {"ticker": ticker, "as_of": as_of}
        _apply(kwargs, vrow, _VALUATION_MAP)
        _apply(kwargs, fin.get(ticker), _FINANCIAL_MAP)
        _apply(kwargs, own.get(ticker), _OWNERSHIP_MAP)
        _apply(kwargs, ovr.get(ticker), _OVERVIEW_MAP)
        out[ticker] = Fundamentals(**kwargs)

    logger.info("Fetched finviz fundamentals for %d tickers (index=%s)", len(out), index)
    return out
