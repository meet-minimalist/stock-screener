from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

SP500_CACHE = Path("data/tickers/sp500.csv")

# Broad-market benchmark that sectors are measured against.
MARKET_BENCHMARK = "SPY"

# GICS sector (as spelled in the Wikipedia S&P 500 table) -> SPDR sector ETF.
# These 11 ETFs are the standard investable proxy for each GICS sector.
SECTOR_ETF = {
    "Information Technology": "XLK",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Consumer Discretionary": "XLY",
    "Communication Services": "XLC",
    "Industrials": "XLI",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Materials": "XLB",
}

# Reverse map + case-insensitive aliases for convenient CLI input ("tech", "xlk").
_ALIASES = {
    "tech": "Information Technology",
    "technology": "Information Technology",
    "it": "Information Technology",
    "financial": "Financials",
    "finance": "Financials",
    "healthcare": "Health Care",
    "health": "Health Care",
    "discretionary": "Consumer Discretionary",
    "staples": "Consumer Staples",
    "comm": "Communication Services",
    "communications": "Communication Services",
    "realestate": "Real Estate",
}


def sector_names() -> list[str]:
    return list(SECTOR_ETF)


def resolve_sector(name: str) -> str:
    """Map user input (sector name, alias, or ETF ticker) to a canonical GICS sector."""
    if not name:
        raise ValueError("Empty sector name")
    raw = name.strip()
    # Exact GICS name.
    for gics in SECTOR_ETF:
        if raw.lower() == gics.lower():
            return gics
    # ETF ticker (XLK -> Information Technology).
    upper = raw.upper()
    for gics, etf in SECTOR_ETF.items():
        if upper == etf:
            return gics
    # Alias.
    key = raw.lower().replace(" ", "").replace("-", "")
    if key in _ALIASES:
        return _ALIASES[key]
    raise ValueError(
        f"Unknown sector '{name}'. Valid: {', '.join(SECTOR_ETF)} (or their ETF tickers)."
    )


def etf_for_sector(sector: str) -> str:
    return SECTOR_ETF[resolve_sector(sector)]


def load_constituents(sector: str | None = None) -> pd.DataFrame:
    """Return S&P 500 constituents with Symbol + GICS Sector, optionally filtered.

    Symbols are normalised the same way as the universe loader (``.`` -> ``-``)
    so they match the yfinance/cache convention (e.g. ``BRK.B`` -> ``BRK-B``).
    """
    if not SP500_CACHE.exists():
        raise FileNotFoundError(
            f"{SP500_CACHE} not found. Run the S&P 500 universe fetch first."
        )
    df = pd.read_csv(SP500_CACHE)
    if "GICS Sector" not in df.columns:
        raise ValueError(f"{SP500_CACHE} has no 'GICS Sector' column.")
    df = df[["Symbol", "Security", "GICS Sector"]].copy()
    df["Symbol"] = df["Symbol"].str.replace(".", "-", regex=False).str.strip()
    if sector is not None:
        canonical = resolve_sector(sector)
        df = df[df["GICS Sector"] == canonical]
    return df.reset_index(drop=True)
