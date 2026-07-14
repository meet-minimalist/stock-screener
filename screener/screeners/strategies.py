from __future__ import annotations

from typing import Any

import pandas as pd
from pandas_ta.candle.cdl_pattern import ALL_PATTERNS, cdl_pattern

from screener.screeners.base import Screener, Signal


DEFAULT_CDL_PATTERNS = ["engulfing", "hammer", "morningstar", "3whitesoldiers", "piercing"]

pd.options.mode.chained_assignment = None


def _find_crossover(df: pd.DataFrame, col1: str, col2: str) -> pd.Series | None:
    fast = df[col1].dropna()
    slow = df[col2].dropna()
    idx = fast.index.intersection(slow.index)
    fast, slow = fast.loc[idx], slow.loc[idx]
    above = fast > slow
    if above.sum() == 0:
        return None
    cross_idx = idx[above]
    return cross_idx[-1:] if len(cross_idx) > 0 else None


def _find_cross_above(df: pd.DataFrame, col1: str, col2: str) -> pd.Series | None:
    fast = df[col1].dropna()
    slow = df[col2].dropna()
    idx = fast.index.intersection(slow.index)
    fast, slow = fast.loc[idx], slow.loc[idx]
    prev_above = (fast.shift(1) > slow.shift(1))
    curr_above = (fast > slow)
    cross = (~prev_above) & curr_above
    if cross.sum() == 0:
        return None
    cross_idx = cross[cross].index
    return cross_idx[[-1]]


def _find_cross_below(df: pd.DataFrame, col1: str, col2: str) -> pd.Series | None:
    fast = df[col1].dropna()
    slow = df[col2].dropna()
    idx = fast.index.intersection(slow.index)
    fast, slow = fast.loc[idx], slow.loc[idx]
    prev_below = (fast.shift(1) < slow.shift(1))
    curr_below = (fast < slow)
    cross = (~prev_below) & curr_below
    if cross.sum() == 0:
        return None
    cross_idx = cross[cross].index
    return cross_idx[[-1]]


class OversoldBounce(Screener):
    def __init__(self, rsi_period: int = 14, threshold: float = 30.0):
        self.rsi_period = rsi_period
        self.threshold = threshold
        self._df: pd.DataFrame | None = None

    def filter(self, ticker: str, df: pd.DataFrame) -> dict[str, Any]:
        self._df = df
        col = f"RSI_{self.rsi_period}"
        if df.empty or col not in df.columns:
            return {"ticker": ticker, "signal": Signal.NEUTRAL, "reason": "no_data"}

        latest_rsi = df[col].dropna().iloc[-1]
        signal = Signal.BUY if latest_rsi < self.threshold else Signal.NEUTRAL
        date_col = _get_date_col(df)
        marker_idx = None
        if signal == Signal.BUY:
            oversold = df[df[col] < self.threshold]
            if not oversold.empty:
                marker_idx = oversold.index[-1:]

        return {
            "ticker": ticker,
            "last_price": float(df["Close"].iloc[-1]),
            "rsi": round(float(latest_rsi), 2),
            "signal": signal,
            "reason": f"RSI={latest_rsi:.1f} {'<' if latest_rsi < self.threshold else '>='} {self.threshold}",
            "signal_date": str(marker_idx[0].date()) if marker_idx is not None else None,
            "marker_dates": _dates_from_idx(marker_idx),
        }

    def get_signal_markers(self) -> list[dict]:
        df = self._df
        if df is None or df.empty:
            return []
        col = f"RSI_{self.rsi_period}"
        if col not in df.columns:
            return []
        rsi = df[col].dropna()
        markers = []
        prev_below = (rsi.shift(1) < self.threshold)
        curr_above = (rsi >= self.threshold)
        exit_idx = rsi[prev_below & curr_above].index
        oversold_idx = rsi[rsi < self.threshold].index

        for dt in oversold_idx:
            markers.append(dict(date=dt, type="oversold", text=f"RSI < {self.threshold}"))
        for dt in exit_idx:
            markers.append(dict(date=dt, type="exit_oversold", text=f"RSI >= {self.threshold}"))
        return markers


class BullishMACD(Screener):
    def __init__(self):
        self._df: pd.DataFrame | None = None

    def _macd_cols(self, df: pd.DataFrame) -> tuple[str, str] | None:
        macd_cols = [c for c in df.columns if c.startswith("MACD_") or c == "MACD"]
        signal_cols = [c for c in df.columns if "MACDs" in c]
        if not macd_cols or not signal_cols:
            return None
        return macd_cols[0], signal_cols[0]

    def filter(self, ticker: str, df: pd.DataFrame) -> dict[str, Any]:
        self._df = df
        cols = self._macd_cols(df)
        if df.empty or cols is None:
            return {"ticker": ticker, "signal": Signal.NEUTRAL, "reason": "no_data"}
        macd_col, sig_col = cols
        macd_vals = df[macd_col].dropna()
        sig_vals = df[sig_col].dropna()
        if macd_vals.empty or sig_vals.empty:
            return {"ticker": ticker, "signal": Signal.NEUTRAL, "reason": "no_data"}
        macd_val = macd_vals.iloc[-1]
        sig_val = sig_vals.iloc[-1]
        signal = Signal.BUY if macd_val > sig_val else Signal.SELL if macd_val < sig_val else Signal.NEUTRAL

        cross = _find_cross_above(df, macd_col, sig_col)
        return {
            "ticker": ticker,
            "last_price": float(df["Close"].iloc[-1]),
            "macd": float(round(macd_val, 4)),
            "macd_signal": float(round(sig_val, 4)),
            "signal": signal,
            "reason": f"MACD={macd_val:.4f} {'>' if macd_val > sig_val else '<'} Signal={sig_val:.4f}",
            "signal_date": str(cross[-1].date()) if cross is not None else None,
            "marker_dates": _dates_from_idx(cross),
        }

    def get_signal_markers(self) -> list[dict]:
        df = self._df
        if df is None or df.empty:
            return []
        cols = self._macd_cols(df)
        if cols is None:
            return []
        macd_col, sig_col = cols
        cross_buy = _find_cross_above(df, macd_col, sig_col)
        cross_sell = _find_cross_below(df, macd_col, sig_col)
        markers = []
        if cross_buy is not None:
            for dt in cross_buy:
                markers.append(dict(date=dt, type="macd_buy", text="MACD > Signal"))
        if cross_sell is not None:
            for dt in cross_sell:
                markers.append(dict(date=dt, type="macd_sell", text="MACD < Signal"))
        return markers


class GoldenCross(Screener):
    def __init__(self, fast: int = 20, slow: int = 50):
        self.fast = fast
        self.slow = slow
        self._df: pd.DataFrame | None = None

    def filter(self, ticker: str, df: pd.DataFrame) -> dict[str, Any]:
        self._df = df
        fast_col = f"SMA_{self.fast}"
        slow_col = f"SMA_{self.slow}"
        if df.empty or fast_col not in df.columns or slow_col not in df.columns:
            return {"ticker": ticker, "signal": Signal.NEUTRAL, "reason": "no_data"}

        fast_val = df[fast_col].dropna().iloc[-1]
        slow_val = df[slow_col].dropna().iloc[-1]
        above = fast_val > slow_val
        signal = Signal.BUY if above else Signal.SELL if fast_val < slow_val else Signal.NEUTRAL

        cross = _find_cross_above(df, fast_col, slow_col)
        return {
            "ticker": ticker,
            "last_price": float(df["Close"].iloc[-1]),
            f"sma_{self.fast}": float(round(fast_val, 2)),
            f"sma_{self.slow}": float(round(slow_val, 2)),
            "signal": signal,
            "reason": f"SMA{self.fast}={fast_val:.2f} {'>' if above else '<'} SMA{self.slow}={slow_val:.2f}",
            "signal_date": str(cross[-1].date()) if cross is not None else None,
            "marker_dates": _dates_from_idx(cross),
        }

    def get_signal_markers(self) -> list[dict]:
        df = self._df
        if df is None or df.empty:
            return []
        fast_col = f"SMA_{self.fast}"
        slow_col = f"SMA_{self.slow}"
        cross_buy = _find_cross_above(df, fast_col, slow_col)
        cross_sell = _find_cross_below(df, fast_col, slow_col)
        markers = []
        if cross_buy is not None:
            for dt in cross_buy:
                markers.append(dict(date=dt, type="golden_cross", text=f"SMA{self.fast} > SMA{self.slow}"))
        if cross_sell is not None:
            for dt in cross_sell:
                markers.append(dict(date=dt, type="death_cross", text=f"SMA{self.fast} < SMA{self.slow}"))
        return markers


class Near52WeekHigh(Screener):
    def __init__(self, lookback: int = 252, threshold_pct: float = 5.0):
        self.lookback = lookback
        self.threshold_pct = threshold_pct
        self._df: pd.DataFrame | None = None

    def filter(self, ticker: str, df: pd.DataFrame) -> dict[str, Any]:
        self._df = df
        if df.empty or "Close" not in df.columns:
            return {"ticker": ticker, "signal": Signal.NEUTRAL, "reason": "no_data"}

        close = df["Close"]
        high_52w = close.rolling(window=min(self.lookback, len(close)), min_periods=1).max().iloc[-1]
        low_52w = close.rolling(window=min(self.lookback, len(close)), min_periods=1).min().iloc[-1]
        current = close.iloc[-1]

        pct_from_high = ((high_52w - current) / high_52w) * 100
        pct_from_low = ((current - low_52w) / low_52w) * 100

        near_high = pct_from_high <= self.threshold_pct
        near_low = pct_from_low <= self.threshold_pct

        if near_high:
            signal = Signal.BUY
            reason = f"{pct_from_high:.1f}% below 52w high ({high_52w:.2f})"
        elif near_low:
            signal = Signal.SELL
            reason = f"{pct_from_low:.1f}% above 52w low ({low_52w:.2f})"
        else:
            signal = Signal.NEUTRAL
            reason = f"{pct_from_high:.1f}% from high, {pct_from_low:.1f}% from low"

        return {
            "ticker": ticker,
            "last_price": float(current),
            "high_52w": round(float(high_52w), 2),
            "low_52w": round(float(low_52w), 2),
            "pct_from_high": round(float(pct_from_high), 1),
            "signal": signal,
            "reason": reason,
            "signal_date": str(df.index[-1].date()) if isinstance(df.index, pd.DatetimeIndex) else None,
            "marker_dates": [],
        }

    def get_signal_markers(self) -> list[dict]:
        df = self._df
        if df is None or df.empty:
            return []
        high_52w = df["Close"].rolling(
            window=min(self.lookback, len(df)), min_periods=1
        ).max()
        low_52w = df["Close"].rolling(
            window=min(self.lookback, len(df)), min_periods=1
        ).min()

        markers = []
        high_idx = high_52w.idxmax()
        low_idx = low_52w.idxmin()
        if isinstance(high_idx, pd.Timestamp):
            markers.append(dict(date=high_idx, type="52w_high", text=f"52w High {high_52w.max():.2f}"))
        if isinstance(low_idx, pd.Timestamp) and low_idx != high_idx:
            markers.append(dict(date=low_idx, type="52w_low", text=f"52w Low {low_52w.min():.2f}"))

        close = df["Close"]
        near_high_idx = close[close >= high_52w * (1 - self.threshold_pct / 100)].index
        for dt in near_high_idx[-3:]:
            markers.append(dict(date=dt, type="near_52w_high", text="Near 52w High"))

        return markers


class BigGain(Screener):
    def __init__(self, threshold_pct: float = 5.0):
        self.threshold_pct = threshold_pct
        self._df: pd.DataFrame | None = None

    def filter(self, ticker: str, df: pd.DataFrame) -> dict[str, Any]:
        self._df = df
        if df.empty or "Close" not in df.columns:
            return {"ticker": ticker, "signal": Signal.NEUTRAL, "reason": "no_data"}

        df = df.copy()
        df["pct_change"] = df["Close"].pct_change() * 100
        latest = df["pct_change"].dropna()
        if latest.empty:
            return {"ticker": ticker, "signal": Signal.NEUTRAL, "reason": "no_data"}

        latest_val = latest.iloc[-1]
        signal = Signal.BUY if latest_val >= self.threshold_pct else Signal.NEUTRAL

        return {
            "ticker": ticker,
            "last_price": float(df["Close"].iloc[-1]),
            "pct_change": round(float(latest_val), 2),
            "signal": signal,
            "reason": f"{'+' if latest_val >= 0 else ''}{latest_val:.1f}% today",
            "signal_date": str(df.index[-1].date()) if isinstance(df.index, pd.DatetimeIndex) else None,
            "marker_dates": [],
        }

    def get_signal_markers(self) -> list[dict]:
        df = self._df
        if df is None or df.empty:
            return []
        df = df.copy()
        df["pct_change"] = df["Close"].pct_change() * 100
        big_gain_idx = df[df["pct_change"] >= self.threshold_pct].index
        markers = []
        for dt in big_gain_idx[-5:]:
            pct = float(df.loc[dt, "pct_change"])
            markers.append(dict(date=dt, type="big_gain", text=f"+{pct:.1f}%"))
        return markers


class HighVolume(Screener):
    def __init__(self, volume_avg_days: int = 20, factor: float = 2.0):
        self.volume_avg_days = volume_avg_days
        self.factor = factor
        self._df: pd.DataFrame | None = None

    def filter(self, ticker: str, df: pd.DataFrame) -> dict[str, Any]:
        self._df = df
        if df.empty or "Volume" not in df.columns or "Close" not in df.columns:
            return {"ticker": ticker, "signal": Signal.NEUTRAL, "reason": "no_data"}

        df = df.copy()
        vol_col = f"Volume_SMA_{self.volume_avg_days}"
        df[vol_col] = df["Volume"].rolling(window=self.volume_avg_days).mean()

        latest_vol = df["Volume"].dropna()
        latest_avg = df[vol_col].dropna()
        if latest_vol.empty or latest_avg.empty:
            return {"ticker": ticker, "signal": Signal.NEUTRAL, "reason": "no_data"}

        latest_vol_val = latest_vol.iloc[-1]
        latest_avg_val = latest_avg.iloc[-1]
        ratio = latest_vol_val / latest_avg_val if latest_avg_val > 0 else 0.0
        signal = Signal.BUY if ratio >= self.factor else Signal.NEUTRAL

        return {
            "ticker": ticker,
            "last_price": float(df["Close"].iloc[-1]),
            "volume_ratio": round(float(ratio), 2),
            "volume": int(latest_vol_val),
            f"volume_sma_{self.volume_avg_days}": int(latest_avg_val),
            "signal": signal,
            "reason": f"Volume {ratio:.1f}x SMA{self.volume_avg_days}",
            "signal_date": str(df.index[-1].date()) if isinstance(df.index, pd.DatetimeIndex) else None,
            "marker_dates": [],
        }

    def get_signal_markers(self) -> list[dict]:
        df = self._df
        if df is None or df.empty:
            return []
        df = df.copy()
        vol_col = f"Volume_SMA_{self.volume_avg_days}"
        df[vol_col] = df["Volume"].rolling(window=self.volume_avg_days).mean()
        high_vol_idx = df[(df["Volume"] > df[vol_col] * self.factor)].index
        markers = []
        for dt in high_vol_idx[-5:]:
            ratio = float(df.loc[dt, "Volume"]) / float(df.loc[dt, vol_col])
            markers.append(dict(date=dt, type="high_volume", text=f"Vol {ratio:.1f}x avg"))
        return markers


CUSTOM_CDL_LABELS = {
    "2crows": "Two Crows",
    "3blackcrows": "Three Black Crows",
    "3inside": "Three Inside",
    "3linestrike": "Three Line Strike",
    "3outside": "Three Outside",
    "3starsinsouth": "Three Stars In South",
    "3whitesoldiers": "Three White Soldiers",
    "abandonedbaby": "Abandoned Baby",
    "advanceblock": "Advance Block",
    "belthold": "Belt Hold",
    "breakaway": "Breakaway",
    "closingmarubozu": "Closing Marubozu",
    "concealbabyswall": "Conceal Baby Swallow",
    "counterattack": "Counterattack",
    "darkcloudcover": "Dark Cloud Cover",
    "doji": "Doji",
    "dojistar": "Doji Star",
    "dragonflydoji": "Dragonfly Doji",
    "engulfing": "Engulfing",
    "eveningdojistar": "Evening Doji Star",
    "eveningstar": "Evening Star",
    "gapsidesidewhite": "Gap Side Side White",
    "gravestonedoji": "Gravestone Doji",
    "hammer": "Hammer",
    "hangingman": "Hanging Man",
    "harami": "Harami",
    "haramicross": "Harami Cross",
    "highwave": "High Wave",
    "hikkake": "Hikkake",
    "hikkakemod": "Hikkake Modified",
    "homingpigeon": "Homing Pigeon",
    "identical3crows": "Identical Three Crows",
    "inneck": "In Neck",
    "inside": "Inside",
    "invertedhammer": "Inverted Hammer",
    "kicking": "Kicking",
    "kickingbylength": "Kicking By Length",
    "ladderbottom": "Ladder Bottom",
    "longleggeddoji": "Long Legged Doji",
    "longline": "Long Line",
    "marubozu": "Marubozu",
    "matchinglow": "Matching Low",
    "mathold": "Mat Hold",
    "morningdojistar": "Morning Doji Star",
    "morningstar": "Morning Star",
    "onneck": "On Neck",
    "piercing": "Piercing",
    "rickshawman": "Rickshaw Man",
    "risefall3methods": "Rise Fall 3 Methods",
    "separatinglines": "Separating Lines",
    "shootingstar": "Shooting Star",
    "shortline": "Short Line",
    "spinningtop": "Spinning Top",
    "stalledpattern": "Stalled Pattern",
    "sticksandwich": "Stick Sandwich",
    "takuri": "Takuri",
    "tasukigap": "Tasuki Gap",
    "thrusting": "Thrusting",
    "tristar": "Tri Star",
    "unique3river": "Unique 3 River",
    "upsidegap2crows": "Upside Gap 2 Crows",
    "xsidegap3methods": "X Side Gap 3 Methods",
}

BULLISH_CDL_PATTERNS = {
    "hammer", "invertedhammer", "bullish_engulfing", "piercing", "morningstar",
    "morningdojistar", "3whitesoldiers", "abandonedbaby", "harami",
    "haramicross", "dragonflydoji", "unique3river", "mathold",
    "ladderbottom", "separatinglines", "sticksandwich", "homingpigeon",
    "breakaway", "matchinglow", "risefall3methods_rising",
}

BEARISH_CDL_PATTERNS = {
    "shootingstar", "hangingman", "bearish_engulfing", "darkcloudcover",
    "eveningstar", "eveningdojistar", "3blackcrows", "2crows",
    "advanceblock", "deliberation", "concealbabyswall", "stalledpattern",
    "gravestonedoji", "counterattack", "breakaway_bearish",
    "risefall3methods_falling", "identical3crows", "onneck", "inneck",
    "thrusting", "tristar_bearish", "xsidegap3methods",
}


class CandlePattern(Screener):
    def __init__(self, patterns: list[str] | None = None):
        self.patterns = patterns or DEFAULT_CDL_PATTERNS
        self._df: pd.DataFrame | None = None
        self._pattern_results: pd.DataFrame | None = None

    def filter(self, ticker: str, df: pd.DataFrame) -> dict[str, Any]:
        self._df = df
        if df.empty or "Open" not in df.columns:
            return {"ticker": ticker, "signal": Signal.NEUTRAL, "reason": "no_data"}

        valid = [p for p in self.patterns if p in ALL_PATTERNS]
        if not valid:
            return {"ticker": ticker, "signal": Signal.NEUTRAL, "reason": "no_valid_patterns"}

        pattern_df = cdl_pattern(df["Open"], df["High"], df["Low"], df["Close"], name=valid)
        self._pattern_results = pattern_df

        if pattern_df.empty:
            return {"ticker": ticker, "signal": Signal.NEUTRAL, "reason": "no_pattern_data"}

        row = pattern_df.iloc[-1]
        detected = [(col, val) for col, val in row.items() if val != 0]

        if not detected:
            return {
                "ticker": ticker,
                "last_price": float(df["Close"].iloc[-1]),
                "signal": Signal.NEUTRAL,
                "reason": "No pattern detected",
                "signal_date": str(df.index[-1].date()) if isinstance(df.index, pd.DatetimeIndex) else None,
                "marker_dates": [],
            }

        bullish = any(v > 0 for _, v in detected)
        bearish = any(v < 0 for _, v in detected)

        if bullish and not bearish:
            signal = Signal.BUY
        elif bearish and not bullish:
            signal = Signal.SELL
        else:
            signal = Signal.NEUTRAL

        pattern_names = []
        for col, val in detected:
            raw_name = col.replace("CDL_", "").lower()
            base_name = raw_name.split("_")[0]
            label = CUSTOM_CDL_LABELS.get(base_name, CUSTOM_CDL_LABELS.get(raw_name, raw_name))
            direction = "Bullish" if val > 0 else "Bearish"
            pattern_names.append(f"{direction} {label}")

        reason = "; ".join(pattern_names)

        return {
            "ticker": ticker,
            "last_price": float(df["Close"].iloc[-1]),
            "signal": signal,
            "reason": reason,
            "signal_date": str(df.index[-1].date()) if isinstance(df.index, pd.DatetimeIndex) else None,
            "marker_dates": [],
        }

    def get_signal_markers(self) -> list[dict]:
        df = self._df
        if df is None or df.empty:
            return []
        if self._pattern_results is None:
            valid = [p for p in self.patterns if p in ALL_PATTERNS]
            if valid:
                self._pattern_results = cdl_pattern(
                    df["Open"], df["High"], df["Low"], df["Close"], name=valid
                )
        if self._pattern_results is None or self._pattern_results.empty:
            return []

        markers = []
        for col in self._pattern_results.columns:
            raw_name = col.replace("CDL_", "").lower()
            base_name = raw_name.split("_")[0]
            label = CUSTOM_CDL_LABELS.get(base_name, CUSTOM_CDL_LABELS.get(raw_name, raw_name))
            hits = self._pattern_results[col]
            for dt in hits[hits != 0].index[-5:]:
                val = hits.loc[dt]
                direction = "Bullish" if val > 0 else "Bearish"
                markers.append(dict(
                    date=dt,
                    type="cdl_pattern",
                    text=f"{direction} {label}",
                    subtype="bullish" if val > 0 else "bearish",
                ))
        return markers


def _get_date_col(df: pd.DataFrame) -> str:
    if isinstance(df.index, pd.DatetimeIndex):
        return df.index.name or "Date"
    return df.columns[0]


def _dates_from_idx(idx: pd.Index | None) -> list[str]:
    if idx is None or len(idx) == 0:
        return []
    return [str(d.date()) for d in idx]
