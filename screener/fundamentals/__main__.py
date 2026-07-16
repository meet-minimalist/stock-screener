"""Refresh a market's fundamentals snapshot: ``python -m screener.fundamentals``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from screener.data.sectors import load_constituents
from screener.data.universe import get_ticker_list
from screener.fundamentals import refresh_market
from screener.markets import get_market


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh fundamentals snapshot")
    parser.add_argument("--market", default="us", help="Market key: us or in")
    parser.add_argument("--universe", default=None,
                        help="Ticker universe (defaults to the market's own, e.g. sp1500 / nifty_total)")
    parser.add_argument("--chunk-size", type=int, default=100,
                        help="Tickers per finviz query (US, keeps the URL short)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s | %(message)s",
    )

    mkt = get_market(args.market)
    tickers = get_ticker_list(args.universe or mkt.universe)

    # Fetch by our own (correct) universe symbols so results key back to them.
    kwargs: dict = {"tickers": tickers}
    if mkt.key == "us":
        kwargs["chunk_size"] = args.chunk_size          # finviz ticker-list chunks
    else:
        # Attach the NSE Industry so India records carry a sector for the screener.
        con = load_constituents(market=mkt.key)
        kwargs["sectors"] = dict(zip(con["Symbol"], con["sector"]))

    funds = refresh_market(mkt.key, **kwargs)
    print(f"Refreshed {len(funds)} {mkt.label} fundamentals -> data/fundamentals/{mkt.key}/")


if __name__ == "__main__":
    main()
