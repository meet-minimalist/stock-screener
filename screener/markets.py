from __future__ import annotations

from collections.abc import Callable, Iterable
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
    # (threshold, label) pairs, descending — the first threshold a market cap
    # clears names its tier. Units match this market's ``market_cap`` (USD for the
    # US, ₹ crore for India).
    cap_tiers: tuple[tuple[float, str], ...] = ()

    def cap_tier(self, market_cap: float | None) -> str | None:
        """Classify a market cap into a size segment (Mega/Large/Mid/Small/…)."""
        if market_cap is None:
            return None
        for threshold, label in self.cap_tiers:
            if market_cap >= threshold:
                return label
        return None


# US uses the conventional absolute-USD bands; India uses ₹-crore bands.
_US_CAP_TIERS = (
    (200e9, "Mega"), (10e9, "Large"), (2e9, "Mid"), (300e6, "Small"), (0.0, "Micro"),
)
_IN_CAP_TIERS = (
    (20000.0, "Large"), (5000.0, "Mid"), (500.0, "Small"), (0.0, "Micro"),
)


US = Market(
    key="us",
    label="US",
    currency="$",
    benchmark=_US_BENCHMARK,          # SPY
    sector_index=_US_SECTOR_ETF,      # GICS sector -> SPDR ETF
    universe="sp1500",
    ticker_suffix="",
    fundamentals_source="finviz",
    cap_tiers=_US_CAP_TIERS,
)

# NSE macro-sector -> a tradeable Nifty sector index on yfinance. Coverage is
# uneven; the RRG builds a constituent composite where an index returns no data.
_IN_SECTOR_INDEX = {
    "Information Technology": "^CNXIT",
    "Financial Services": "^NSEBANK",   # Bank Nifty as a reliable financials proxy
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
    cap_tiers=_IN_CAP_TIERS,
)

MARKETS: dict[str, Market] = {US.key: US, INDIA.key: INDIA}

# India large/mid/small is officially rank-based (SEBI): top 100 by market cap are
# large, the next 150 mid, the rest small. We hold the whole Nifty Total Market
# universe, so deriving the cutoffs from its distribution self-calibrates as caps
# drift — far sturdier than fixed rupee thresholds. Fewer names than this and we
# fall back to the absolute bands.
_IN_RANK_LARGE = 100
_IN_RANK_MID = 250
_MIN_UNIVERSE_FOR_RANKS = _IN_RANK_LARGE


def cap_classifier(market: Market,
                   universe_caps: Iterable[float | None] = ()) -> Callable[[float | None], str | None]:
    """Return a market-cap → size-segment function for ``market``.

    US uses fixed absolute-USD bands. India ranks the supplied universe (SEBI-style)
    so the cutoffs track the market; if too few caps are supplied it falls back to
    ``market.cap_tier``.
    """
    if market.key != "in":
        return market.cap_tier
    caps = sorted((c for c in universe_caps if c is not None), reverse=True)
    if len(caps) < _MIN_UNIVERSE_FOR_RANKS:
        return market.cap_tier
    large_cut = caps[_IN_RANK_LARGE - 1]
    mid_cut = caps[min(_IN_RANK_MID, len(caps)) - 1]

    def classify(mc: float | None) -> str | None:
        if mc is None:
            return None
        if mc >= large_cut:
            return "Large"
        if mc >= mid_cut:
            return "Mid"
        return "Small"

    return classify


def get_market(key: str) -> Market:
    k = (key or "us").lower()
    if k not in MARKETS:
        raise ValueError(f"Unknown market '{key}'. Known: {', '.join(MARKETS)}")
    return MARKETS[k]
