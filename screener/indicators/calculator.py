from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    def compute(self, df: pd.DataFrame, sma_periods: Optional[list[int]] = None,
                rsi_periods: Optional[list[int]] = None,
                macd_config: Optional[dict] = None) -> pd.DataFrame:
        if df.empty:
            return df

        result = df.copy()

        if sma_periods:
            for p in sma_periods:
                col = f"SMA_{p}"
                if col not in result.columns:
                    sma = ta.sma(result["Close"], length=p)
                    if sma is not None:
                        result[col] = sma

        if rsi_periods:
            for p in rsi_periods:
                col = f"RSI_{p}"
                if col not in result.columns:
                    rsi = ta.rsi(result["Close"], length=p)
                    if rsi is not None:
                        result[col] = rsi

        if macd_config:
            if "MACD" not in result.columns:
                fast = macd_config.get("fast", 12)
                slow = macd_config.get("slow", 26)
                signal = macd_config.get("signal", 9)
                macd = ta.macd(result["Close"], fast=fast, slow=slow, signal=signal)
                if macd is not None:
                    result = pd.concat([result, macd], axis=1)

        return result
