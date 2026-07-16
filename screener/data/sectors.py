from __future__ import annotations

import logging

import pandas as pd

from screener.paths import TICKERS_DIR

logger = logging.getLogger(__name__)

SP500_CACHE = TICKERS_DIR / "sp500.csv"
# Any of these cached tier files contribute to the ticker -> GICS sector map.
_CONSTITUENT_TIERS = ("sp500", "sp400", "sp600")

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


def load_constituents(sector: str | None = None, market: str = "us") -> pd.DataFrame:
    """Return index constituents as Symbol / Security / sector, optionally filtered.

    - **US**: merges every cached S&P tier (500/400/600) present; sector is the
      GICS Sector; symbols normalised ``.`` -> ``-`` (yfinance convention).
    - **India**: reads the cached Nifty Total Market list; sector is NSE's
      Industry column; symbols kept as the bare NSE symbol.
    """
    market = market.lower()
    if market == "us":
        frames = []
        for tier in _CONSTITUENT_TIERS:
            path = TICKERS_DIR / f"{tier}.csv"
            if path.exists():
                df = pd.read_csv(path)
                if "GICS Sector" in df.columns:
                    frames.append(df[["Symbol", "Security", "GICS Sector"]]
                                  .rename(columns={"GICS Sector": "sector"}))
        if not frames:
            raise FileNotFoundError(
                f"No S&P constituent files in {TICKERS_DIR}. Run the universe fetch first.")
        df = pd.concat(frames, ignore_index=True)
        df["Symbol"] = df["Symbol"].astype(str).str.replace(".", "-", regex=False).str.strip()
    else:
        path = TICKERS_DIR / "nifty_total.csv"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Run the Nifty universe fetch first.")
        df = (pd.read_csv(path)
              .rename(columns={"Company Name": "Security", "Industry": "sector"})
              [["Symbol", "Security", "sector"]])
        df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()

    df = df.drop_duplicates(subset="Symbol")
    if sector is not None:
        canonical = resolve_sector(sector) if market == "us" else sector
        df = df[df["sector"] == canonical]
    return df.reset_index(drop=True)
