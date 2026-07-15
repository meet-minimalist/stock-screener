from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path

import pandas as pd

from screener.fundamentals.schema import Fundamentals
from screener.paths import FUNDAMENTALS_DIR

logger = logging.getLogger(__name__)

# Timestamped snapshots accumulate under data/fundamentals/<market>/ — finviz and
# screener.in keep no history, so these snapshots become our own historical
# fundamentals dataset over time.


def _market_dir(market: str) -> Path:
    return FUNDAMENTALS_DIR / market.lower()


def save_snapshot(market: str, funds: dict[str, Fundamentals],
                  as_of: str | None = None) -> Path:
    """Write a dated snapshot plus an overwriting ``latest.csv``. Returns the dated path."""
    market_dir = _market_dir(market)
    market_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame([f.to_row() for f in funds.values()])
    date = as_of or _dt.date.today().isoformat()
    dated = market_dir / f"{date}.csv"
    df.to_csv(dated, index=False)
    df.to_csv(market_dir / "latest.csv", index=False)
    logger.info("Saved %d fundamentals rows to %s", len(df), dated)
    return dated


def load_latest(market: str) -> dict[str, Fundamentals]:
    """Load the most recent snapshot as ``{ticker: Fundamentals}`` (empty if none)."""
    path = _market_dir(market) / "latest.csv"
    if not path.exists():
        logger.warning("No fundamentals snapshot at %s", path)
        return {}
    df = pd.read_csv(path)
    return {
        str(row["ticker"]): Fundamentals.from_row(row.to_dict())
        for _, row in df.iterrows()
    }
