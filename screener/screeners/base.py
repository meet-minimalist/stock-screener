from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class Screener(ABC):
    @abstractmethod
    def filter(self, ticker: str, df: pd.DataFrame) -> dict[str, Any]:
        ...


class Signal:
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"
