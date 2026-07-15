"""Fundamental-data layer: fetch, snapshot, and serve company fundamentals.

Market-keyed so additional markets (e.g. India via screener.in) attach without
touching the daily pipeline. Only the US/finviz source is implemented today.
"""

from screener.fundamentals.schema import Fundamentals
from screener.fundamentals.service import get_fundamentals, refresh_market

__all__ = ["Fundamentals", "get_fundamentals", "refresh_market"]
