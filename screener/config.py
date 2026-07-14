from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Condition:
    indicator: str
    operator: str
    value: Optional[float] = None
    value_column: Optional[str] = None


@dataclass
class Strategy:
    name: str
    conditions: list[Condition] = field(default_factory=list)


@dataclass
class IndicatorConfig:
    sma: list[int] = field(default_factory=list)
    rsi: list[int] = field(default_factory=list)
    macd: Optional[dict] = None


@dataclass
class ScreenConfig:
    universe: str = "sp500"
    start_date: str = "2025-06-22"
    end_date: str = "2026-06-22"
    interval: str = "1d"
    indicators: IndicatorConfig = field(default_factory=IndicatorConfig)
    strategies: dict[str, Strategy] = field(default_factory=dict)
    cache_dir: str = "data/yfinance_cache"

    @classmethod
    def from_yaml(cls, path: str | Path) -> ScreenConfig:
        path = Path(path)
        if not path.exists():
            logger.info("No config found at %s, using defaults", path)
            return cls()

        with open(path) as f:
            raw = yaml.safe_load(f)

        if raw is None:
            return cls()

        indicators_raw = raw.get("indicators", {})
        indicators = IndicatorConfig(
            sma=indicators_raw.get("sma", []),
            rsi=indicators_raw.get("rsi", []),
            macd=indicators_raw.get("macd"),
        )

        strategies_raw = raw.get("strategies", {})
        strategies = {}
        for name, s_raw in strategies_raw.items():
            conditions = []
            for c in s_raw.get("conditions", []):
                conditions.append(
                    Condition(
                        indicator=c["indicator"],
                        operator=c["operator"],
                        value=c.get("value"),
                        value_column=c.get("value_column"),
                    )
                )
            strategies[name] = Strategy(name=name, conditions=conditions)

        return cls(
            universe=raw.get("universe", cls.universe),
            start_date=raw.get("start_date", cls.start_date),
            end_date=raw.get("end_date", cls.end_date),
            interval=raw.get("interval", cls.interval),
            indicators=indicators,
            strategies=strategies,
            cache_dir=raw.get("cache_dir", cls.cache_dir),
        )
