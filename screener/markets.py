from __future__ import annotations

from dataclasses import dataclass

from screener.data.sectors import MARKET_BENCHMARK as _US_BENCHMARK
from screener.data.sectors import SECTOR_ETF as _US_SECTOR_ETF


@dataclass(frozen=True)
class Market:
    """Everything country-specific about one market, so the pipeline stays generic.

    ``sector_index`` maps a sector name (as it appears in that market's constituent
    data) to the ticker of a tradeable index/ETF used as the sector's RRG proxy.
    ``ticker_suffix`` is appended to a symbol for price lookups (e.g. ``.NS`` for
    NSE on yfinance) while records stay keyed by the bare symbol.
    """
    key: str
    label: str
    currency: str
    benchmark: str
    sector_index: dict[str, str]
    universe: str
    ticker_suffix: str = ""
    fundamentals_source: str = ""


US = Market(
    key="us",
    label="US",
    currency="$",
    benchmark=_US_BENCHMARK,          # SPY
    sector_index=_US_SECTOR_ETF,      # GICS sector -> SPDR ETF
    universe="sp1500",
    ticker_suffix="",
    fundamentals_source="finviz",
)

# NSE macro-sector -> a tradeable Nifty sector index on yfinance. Coverage is
# uneven; the RRG builds a constituent composite where an index returns no data.
_IN_SECTOR_INDEX = {
    "Information Technology": "^CNXIT",
    "Financial Services": "NIFTY_FIN_SERVICE",
    "Fast Moving Consumer Goods": "^CNXFMCG",
    "Automobile and Auto Components": "^CNXAUTO",
    "Healthcare": "^CNXPHARMA",
    "Metals & Mining": "^CNXMETAL",
    "Oil Gas & Consumable Fuels": "^CNXENERGY",
    "Realty": "^CNXREALTY",
    "Media Entertainment & Publication": "^CNXMEDIA",
    "Power": "^CNXINFRA",
}

INDIA = Market(
    key="in",
    label="India",
    currency="₹",
    benchmark="^NSEI",                # Nifty 50 (fallback ^CRSLDX = Nifty 500)
    sector_index=_IN_SECTOR_INDEX,
    universe="nifty_total",
    ticker_suffix=".NS",
    fundamentals_source="screener_in",
)

MARKETS: dict[str, Market] = {US.key: US, INDIA.key: INDIA}


def get_market(key: str) -> Market:
    k = (key or "us").lower()
    if k not in MARKETS:
        raise ValueError(f"Unknown market '{key}'. Known: {', '.join(MARKETS)}")
    return MARKETS[k]
