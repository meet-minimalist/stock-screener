"""Single source of truth for on-disk data locations.

Everything the app downloads or accumulates lives under one ``data/`` root,
subdivided by concern. New data types should add a constant here rather than
inventing their own top-level folder, so storage stays organised.

Layout::

    data/
      yfinance_cache/   price cache            (gitignored — ephemeral)
      tickers/          universe lists         (committed — reference)
      uploads/          user-uploaded CSVs     (gitignored)
      fundamentals/     fundamentals snapshots (committed — accumulated dataset)
"""

from __future__ import annotations

from pathlib import Path

DATA_ROOT = Path("data")

PRICE_CACHE_DIR = DATA_ROOT / "yfinance_cache"
TICKERS_DIR = DATA_ROOT / "tickers"
UPLOADS_DIR = DATA_ROOT / "uploads"
FUNDAMENTALS_DIR = DATA_ROOT / "fundamentals"
