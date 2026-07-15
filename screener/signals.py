from __future__ import annotations

import logging

import pandas as pd

from screener.screeners.strategies import (
    BigGain,
    BullishMACD,
    CandlePattern,
    GoldenCross,
    HighVolume,
    Near52WeekHigh,
    OversoldBounce,
    VolatileUptrend,
)

logger = logging.getLogger(__name__)

# Reuse the existing, tested strategies as-is; each maps to a screen tab. The
# key is the stable screen id used by the screens registry and the UI.
def _build_strategies() -> dict:
    return {
        "oversold_bounce": OversoldBounce(),
        "bullish_macd": BullishMACD(),
        "golden_cross": GoldenCross(),
        "near_52w_high": Near52WeekHigh(threshold_pct=3.0),
        "big_gain": BigGain(threshold_pct=5.0),
        "high_volume": HighVolume(factor=2.0),
        "candle_patterns": CandlePattern(),
        "volatile_uptrend": VolatileUptrend(),
    }


def compute_signals(ticker: str, df: pd.DataFrame) -> tuple[dict[str, str], dict[str, str]]:
    """Run every strategy over ``df`` and return ``(signals, notes)``.

    ``signals`` is ``{screen_id: BUY/SELL/NEUTRAL}``; ``notes`` is
    ``{screen_id: reason}`` for the strategies that fired BUY (e.g. the specific
    candlestick pattern, or "SMA20 > SMA50") so each screen tab can explain itself.

    Requires the indicators the strategies read (RSI_14, SMA_20/50, MACD) to be
    present on ``df``. Each strategy is isolated: if one raises (e.g. candlestick
    recognition without TA-Lib), it degrades to NEUTRAL instead of failing the row.
    """
    signals: dict[str, str] = {}
    notes: dict[str, str] = {}
    for name, strategy in _build_strategies().items():
        try:
            result = strategy.filter(ticker, df)
            signal = result.get("signal", "NEUTRAL")
            signals[name] = signal
            if signal == "BUY" and result.get("reason"):
                notes[name] = result["reason"]
        except Exception as exc:  # keep one bad strategy from sinking the row
            logger.debug("Strategy %s failed for %s: %s", name, ticker, exc)
            signals[name] = "NEUTRAL"
    return signals, notes
