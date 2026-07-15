from __future__ import annotations

from dataclasses import asdict, dataclass, field

# The single shared domain object: one scored stock. The scorer produces these,
# the screens registry filters them, and the web/report layers render them (via
# to_dict). Keeping one typed record avoids ad-hoc dicts drifting apart.


@dataclass
class StockRecord:
    ticker: str
    sector: str | None = None
    # None score == excluded by a gate; `filtered`/`filter_reason` say why.
    score: float | None = None
    filtered: bool = False
    filter_reason: str | None = None

    # Price / technical context.
    price: float | None = None
    quadrant: str | None = None
    daily_vol: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    ret_12m: float | None = None
    rel_sector_3m: float | None = None

    # Fundamentals (display).
    pe: float | None = None
    peg: float | None = None
    roe: float | None = None
    eps_growth: float | None = None
    debt_equity: float | None = None
    market_cap: float | None = None

    # Ratings + provenance.
    factors: dict[str, float] = field(default_factory=dict)
    triggers: list[str] = field(default_factory=list)
    signals: dict[str, str] = field(default_factory=dict)  # per-strategy BUY/SELL/NEUTRAL
    reason: str = ""

    @property
    def passed(self) -> bool:
        """True when the stock cleared every gate and carries a score."""
        return self.score is not None

    def to_dict(self) -> dict:
        return asdict(self)
