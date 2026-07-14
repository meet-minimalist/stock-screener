from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from tqdm import tqdm

from screener.data.fetcher import DataFetcher
from screener.indicators.calculator import IndicatorCalculator
from screener.screeners.base import Screener

logger = logging.getLogger(__name__)


class ScreeningEngine:
    def __init__(self, cache_dir: str = "data/yfinance_cache"):
        self.fetcher = DataFetcher(cache_dir=cache_dir)
        self.calculator = IndicatorCalculator()

    def run(
        self,
        tickers: list[str],
        screener: Screener,
        start_date: str,
        end_date: str,
        interval: str = "1d",
        sma_periods: list[int] | None = None,
        rsi_periods: list[int] | None = None,
        macd_config: dict | None = None,
        show_progress: bool = True,
        return_data: bool = False,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        data_map: dict[str, pd.DataFrame] = {}

        iterator = tqdm(tickers, desc="Scanning", unit="ticker") if show_progress else tickers

        for ticker in iterator:
            df = self.fetcher.get_data(ticker, start_date, end_date, interval=interval)
            if df.empty:
                continue

            df = self.calculator.compute(
                df,
                sma_periods=sma_periods,
                rsi_periods=rsi_periods,
                macd_config=macd_config,
            )

            result = screener.filter(ticker, df)
            results.append(result)
            if return_data:
                data_map[ticker] = df

        if return_data:
            return results, data_map
        return results

    @staticmethod
    def to_dataframe(results: list[dict[str, Any]]) -> pd.DataFrame:
        return pd.DataFrame(results)
