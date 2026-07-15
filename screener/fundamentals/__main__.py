"""Refresh a market's fundamentals snapshot: ``python -m screener.fundamentals``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from screener.fundamentals import refresh_market


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh fundamentals snapshot")
    parser.add_argument("--market", default="us", help="Market key (default: us)")
    parser.add_argument("--index", default="S&P 500", help="finviz index filter (US)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s | %(message)s",
    )

    kwargs = {"index": args.index} if args.market == "us" else {}
    funds = refresh_market(args.market, **kwargs)
    print(f"Refreshed {len(funds)} {args.market.upper()} fundamentals -> data/fundamentals/{args.market}/")


if __name__ == "__main__":
    main()
