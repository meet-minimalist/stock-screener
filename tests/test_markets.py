from __future__ import annotations

import pytest

from screener.markets import INDIA, MARKETS, US, Market, get_market


def test_get_market_resolves_known_keys():
    assert get_market("us") is US
    assert get_market("in") is INDIA
    assert get_market("US") is US            # case-insensitive
    assert get_market(None) is US            # default


def test_unknown_market_raises():
    with pytest.raises(ValueError):
        get_market("uk")


def test_market_configs_are_coherent():
    for m in MARKETS.values():
        assert isinstance(m, Market)
        assert m.benchmark and m.universe and m.sector_index
    assert US.ticker_suffix == "" and US.currency == "$"
    assert INDIA.ticker_suffix == ".NS" and INDIA.currency == "₹"
    assert INDIA.benchmark == "^NSEI"
