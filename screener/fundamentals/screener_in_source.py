from __future__ import annotations

import datetime as _dt
import logging
import os

from screener.fundamentals.schema import Fundamentals

logger = logging.getLogger(__name__)


def _num(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value == value else None


def _last(row) -> float | None:
    """Last non-null numeric value across a statement row (most recent period)."""
    for value in reversed(list(row)):
        v = _num(value)
        if v is not None:
            return v
    return None


def _yoy(row) -> float | None:
    """Year-over-year % growth from the last two numeric periods."""
    vals = [v for v in (_num(x) for x in row) if v is not None]
    if len(vals) >= 2 and vals[-2] != 0:
        return (vals[-1] / vals[-2] - 1) * 100.0
    return None


def _cagr(row, years: int) -> float | None:
    """Compound annual growth % over the last ``years`` periods (needs positive ends)."""
    vals = [v for v in (_num(x) for x in row) if v is not None]
    if len(vals) > years:
        start, end = vals[-years - 1], vals[-1]
        if start > 0 and end > 0:
            return ((end / start) ** (1.0 / years) - 1.0) * 100.0
    return None


def _to_fundamentals(company, symbol: str, as_of: str, sector: str | None) -> Fundamentals:
    """Map a screener.in Company (top_ratios + statements) to the shared schema.

    Market cap is in ₹ crore (screener.in's unit); ratios/margins are percents.
    Derived fields are best-effort — any parsing miss leaves them None so grading
    stays graceful.
    """
    tr = company.top_ratios
    price = _num(tr.get("Current Price"))
    book = _num(tr.get("Book Value"))

    net_margin = oper_margin = eps_growth = eps_growth_5y = sales_growth = debt_equity = None
    try:
        pl = company.profit_loss
        if "OPM %" in pl.index:
            oper_margin = _last(pl.loc["OPM %"])
        if "Net Profit" in pl.index and "Sales" in pl.index:
            np_, sales = _last(pl.loc["Net Profit"]), _last(pl.loc["Sales"])
            if np_ is not None and sales:
                net_margin = np_ / sales * 100.0
        # Multi-year CAGR from the full P&L — sturdier than a 2-year YoY.
        if "EPS in Rs" in pl.index:
            eps_growth = _cagr(pl.loc["EPS in Rs"], 3)
            eps_growth_5y = _cagr(pl.loc["EPS in Rs"], 5)
        if "Sales" in pl.index:
            sales_growth = _cagr(pl.loc["Sales"], 3)
    except Exception as exc:
        logger.debug("profit_loss parse failed for %s: %s", symbol, exc)

    promoter_holding = None
    try:
        sh = company.shareholding()          # parsed from the same cached page
        if "Promoters" in sh.index:
            promoter_holding = _last(sh.loc["Promoters"])
    except Exception as exc:
        logger.debug("shareholding parse failed for %s: %s", symbol, exc)
    try:
        bs = company.balance_sheet
        borrow = _last(bs.loc["Borrowings"]) if "Borrowings" in bs.index else None
        equity = sum(v for v in (
            _last(bs.loc["Equity Capital"]) if "Equity Capital" in bs.index else None,
            _last(bs.loc["Reserves"]) if "Reserves" in bs.index else None,
        ) if v is not None)
        if borrow is not None and equity:
            debt_equity = borrow / equity
    except Exception as exc:
        logger.debug("balance_sheet parse failed for %s: %s", symbol, exc)

    return Fundamentals(
        ticker=symbol, as_of=as_of, sector=sector,
        market_cap=_num(tr.get("Market Cap")),
        pe=_num(tr.get("Stock P/E")),
        pb=(price / book) if (price and book) else None,
        roe=_num(tr.get("ROE")),
        roi=_num(tr.get("ROCE")),          # screener.in reports ROCE
        dividend_yield=_num(tr.get("Dividend Yield")),
        net_margin=net_margin, oper_margin=oper_margin,
        eps_growth=eps_growth, eps_growth_5y=eps_growth_5y,
        sales_growth=sales_growth, debt_equity=debt_equity,
        promoter_holding=promoter_holding,
    )


def fetch(tickers, sectors: dict | None = None, sleep_sec: float | None = None,
          **kwargs) -> dict[str, Fundamentals]:
    """Fetch India fundamentals for a symbol list via the private screener.in module.

    One request per company (throttled by the client); optional login via the
    ``SCREENER_EMAIL`` / ``SCREENER_PASSWORD`` env vars unlocks longer history.
    Failures on individual names are logged and skipped.
    """
    from screener_fetcher import ScreenerClient
    from screener_fetcher.exceptions import ScreenerError

    client = ScreenerClient() if sleep_sec is None else ScreenerClient(min_interval=sleep_sec)
    email, password = os.getenv("SCREENER_EMAIL"), os.getenv("SCREENER_PASSWORD")
    if email and password:
        try:
            client.login(email, password)
        except ScreenerError as exc:
            logger.warning("screener.in login failed (continuing without): %s", exc)

    as_of = _dt.date.today().isoformat()
    sectors = sectors or {}
    out: dict[str, Fundamentals] = {}
    for symbol in tickers:
        try:
            company = client.company(symbol)
            out[symbol] = _to_fundamentals(company, symbol, as_of, sectors.get(symbol))
        except ScreenerError as exc:
            logger.warning("screener.in fetch failed for %s: %s", symbol, exc)
        except Exception as exc:  # noqa: BLE001 - keep the batch going
            logger.warning("unexpected error fetching %s: %s", symbol, exc)

    logger.info("Fetched screener.in fundamentals for %d/%d tickers", len(out), len(list(tickers)))
    return out
