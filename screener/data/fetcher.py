from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from yf_cache import YFinanceDataDownloader

logger = logging.getLogger(__name__)


class DataFetcher:
    def __init__(self, cache_dir: str = "data/yfinance_cache"):
        self._downloader = YFinanceDataDownloader(cache_dir=cache_dir)

    def get_data(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        try:
            df = self._downloader.get_data(
                ticker,
                start_date,
                end_date,
                interval=interval,
            )
            if df.empty:
                logger.debug("No data returned for %s", ticker)
            return df
        except Exception as exc:
            logger.warning("Failed to fetch data for %s: %s", ticker, exc)
            return pd.DataFrame()
