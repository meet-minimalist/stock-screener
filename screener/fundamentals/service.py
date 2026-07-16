from __future__ import annotations

import logging
from collections.abc import Iterable

from screener.fundamentals import store
from screener.fundamentals.schema import Fundamentals

logger = logging.getLogger(__name__)


def _fetch_us(**kwargs) -> dict[str, Fundamentals]:
    # Imported lazily so the daily pipeline never needs the sources installed
    # (it only reads the committed snapshot); only refreshes pull the source.
    from screener.fundamentals import finviz_source
    return finviz_source.fetch(**kwargs)


def _fetch_in(**kwargs) -> dict[str, Fundamentals]:
    from screener.fundamentals import screener_in_source
    return screener_in_source.fetch(**kwargs)


# market key -> source fetcher.
_SOURCES = {"us": _fetch_us, "in": _fetch_in}


def refresh_market(market: str = "us", **source_kwargs) -> dict[str, Fundamentals]:
    """Fetch fresh fundamentals from the market's source and snapshot them to disk."""
    market = market.lower()
    if market not in _SOURCES:
        raise ValueError(f"No fundamentals source registered for market '{market}'")
    funds = _SOURCES[market](**source_kwargs)
    store.save_snapshot(market, funds)
    return funds


def get_fundamentals(
    market: str = "us",
    tickers: Iterable[str] | None = None,
    force_refresh: bool = False,
) -> dict[str, Fundamentals]:
    """Return ``{ticker: Fundamentals}`` for a market.

    Reads the latest on-disk snapshot by default (what the daily pipeline uses);
    ``force_refresh`` pulls from the live source first. When ``tickers`` is given,
    the result is limited to those present.
    """
    market = market.lower()
    funds = refresh_market(market) if force_refresh else store.load_latest(market)
    if tickers is not None:
        wanted = {str(t) for t in tickers}
        funds = {t: f for t, f in funds.items() if t in wanted}
    return funds
