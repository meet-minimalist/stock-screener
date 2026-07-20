from __future__ import annotations

import pytest

from screener.markets import INDIA, MARKETS, US, Market, cap_classifier, get_market


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


def test_us_cap_tiers_use_absolute_usd_bands():
    assert US.cap_tier(3.0e12) == "Mega"      # $3T
    assert US.cap_tier(50e9) == "Large"       # $50B
    assert US.cap_tier(5e9) == "Mid"          # $5B
    assert US.cap_tier(1e9) == "Small"        # $1B
    assert US.cap_tier(1e8) == "Micro"        # $100M
    assert US.cap_tier(None) is None


def test_india_absolute_bands_are_the_fallback():
    # Market.cap_tier holds India's absolute rupee-crore bands, used only when the
    # universe is too small to rank; the live pages use the rank-based classifier.
    assert INDIA.cap_tier(1_800_000) == "Large"   # ₹18 lakh cr (Reliance-scale)
    assert INDIA.cap_tier(45_541) == "Large"
    assert INDIA.cap_tier(8_000) == "Mid"
    assert INDIA.cap_tier(3_788) == "Small"
    assert INDIA.cap_tier(200) == "Micro"
    assert INDIA.cap_tier(None) is None


def test_india_segments_are_rank_based():
    caps = [float(x) for x in range(1000, 1300)]   # 300 names
    top = sorted(caps, reverse=True)
    classify = cap_classifier(INDIA, caps)
    assert classify(top[0]) == "Large"    # #1
    assert classify(top[99]) == "Large"   # #100 (large cutoff)
    assert classify(top[100]) == "Mid"    # #101
    assert classify(top[249]) == "Mid"    # #250 (mid cutoff)
    assert classify(top[250]) == "Small"  # #251
    assert classify(None) is None


def test_india_classifier_falls_back_when_universe_too_small():
    classify = cap_classifier(INDIA, [1e5, 2e5])   # < 100 names → absolute bands
    assert classify(45_541) == "Large"
    assert classify(3_788) == "Small"


def test_us_classifier_uses_absolute_bands_regardless_of_universe():
    classify = cap_classifier(US, [])
    assert classify(3.0e12) == "Mega"
    assert classify(5e9) == "Mid"
    assert classify(None) is None
