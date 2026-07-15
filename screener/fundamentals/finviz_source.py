from __future__ import annotations

import datetime as _dt
import logging

from screener.fundamentals.schema import Fundamentals, to_float, to_pct

logger = logging.getLogger(__name__)

# schema field -> (finviz Valuation column, parser). Ratios/absolutes use
# to_float; percentage metrics use to_pct so every % field is on one scale.
_VALUATION_MAP = {
    "market_cap": ("Market Cap", to_float),
    "pe": ("P/E", to_float),
    "peg": ("PEG", to_float),
    "ps": ("P/S", to_float),
    "pb": ("P/B", to_float),
    "eps_growth": ("EPS This Y", to_pct),
    "sales_growth": ("Sales Past 5Y", to_pct),
}
# schema field -> (finviz Financial column, parser)
_FINANCIAL_MAP = {
    "roe": ("ROE", to_pct),
    "roi": ("ROIC", to_pct),
    "net_margin": ("Profit M", to_pct),
    "debt_equity": ("Debt/Eq", to_float),
    "dividend_yield": ("Dividend", to_pct),
}


def _normalise(ticker: str) -> str:
    # Match the universe/yfinance convention (BRK.B -> BRK-B).
    return str(ticker).strip().upper().replace(".", "-")


def fetch(index: str = "S&P 500", limit: int | None = None,
          sleep_sec: float = 1.0) -> dict[str, Fundamentals]:
    """Pull fundamentals for an index in bulk from finviz.

    Uses finvizfinance's Valuation and Financial screener views (paginated
    server-side), merges them per ticker, and maps to the Fundamentals schema.
    ``limit`` caps rows (handy for tests); ``sleep_sec`` paces requests politely.
    """
    from finvizfinance.screener.financial import Financial
    from finvizfinance.screener.valuation import Valuation

    as_of = _dt.date.today().isoformat()
    filters = {"Index": index}

    valuation = Valuation()
    valuation.set_filter(filters_dict=filters)
    df_val = valuation.screener_view(limit=limit, verbose=0, sleep_sec=sleep_sec)

    financial = Financial()
    financial.set_filter(filters_dict=filters)
    df_fin = financial.screener_view(limit=limit, verbose=0, sleep_sec=sleep_sec)

    fin_by_ticker = {_normalise(r["Ticker"]): r for _, r in df_fin.iterrows()}

    out: dict[str, Fundamentals] = {}
    for _, vrow in df_val.iterrows():
        ticker = _normalise(vrow["Ticker"])
        frow = fin_by_ticker.get(ticker)
        kwargs = {"ticker": ticker, "as_of": as_of}
        for field, (col, parse) in _VALUATION_MAP.items():
            kwargs[field] = parse(vrow.get(col))
        for field, (col, parse) in _FINANCIAL_MAP.items():
            kwargs[field] = parse(frow.get(col)) if frow is not None else None
        out[ticker] = Fundamentals(**kwargs)

    logger.info("Fetched finviz fundamentals for %d tickers (index=%s)", len(out), index)
    return out
