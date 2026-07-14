from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from screener.config import ScreenConfig
from screener.data.universe import get_ticker_list
from screener.reports.formatter import export_csv, format_results_table
from screener.screeners.engine import ScreeningEngine
from screener.screeners.strategies import BigGain, BullishMACD, CandlePattern, GoldenCross, HighVolume, Near52WeekHigh, OversoldBounce, VolatileUptrend
from screener.screeners.strategies import DEFAULT_CDL_PATTERNS

STRATEGY_MAP = {
    "oversold_bounce": OversoldBounce,
    "bullish_macd": BullishMACD,
    "golden_cross": GoldenCross,
    "near_52w_high": Near52WeekHigh,
    "big_gain": BigGain,
    "high_volume": HighVolume,
    "candle_patterns": CandlePattern,
    "volatile_uptrend": VolatileUptrend,
}


def main():
    parser = argparse.ArgumentParser(description="Stock Technical Screener")
    parser.add_argument("--config", "-c", type=str, default="config.yaml", help="Path to config YAML")
    parser.add_argument("--universe", "-u", type=str, default=None, help="Ticker universe (sp500, or path to CSV)")
    parser.add_argument("--strategy", "-s", type=str, default="oversold_bounce", choices=list(STRATEGY_MAP) + ["custom"], help="Screening strategy")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--interval", type=str, default=None, help="Data interval (1d, 1h, etc.)")
    parser.add_argument("--cdl-patterns", type=str, default=None,
                        help="Comma-separated candle patterns for candle_patterns strategy")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output CSV path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s | %(name)s | %(message)s",
    )

    config = ScreenConfig.from_yaml(args.config)
    universe_src = args.universe or config.universe
    strategy_name = args.strategy
    start_date = args.start or config.start_date
    end_date = args.end or config.end_date
    interval = args.interval or config.interval

    tickers = get_ticker_list(universe_src)
    if not tickers:
        logging.error("No tickers found for universe '%s'", universe_src)
        sys.exit(1)

    logging.info("Loaded %d tickers from '%s'", len(tickers), universe_src)

    if strategy_name == "custom":
        if strategy_name not in config.strategies:
            logging.error("No custom strategy named '%s' in config", strategy_name)
            sys.exit(1)
        strategy = STRATEGY_MAP["oversold_bounce"]()
    elif strategy_name in STRATEGY_MAP:
        if strategy_name == "candle_patterns":
            patterns = args.cdl_patterns.split(",") if args.cdl_patterns else DEFAULT_CDL_PATTERNS
            strategy = CandlePattern(patterns=patterns)
        else:
            strategy = STRATEGY_MAP[strategy_name]()
    else:
        logging.error("Unknown strategy '%s'", strategy_name)
        sys.exit(1)

    engine = ScreeningEngine(cache_dir=config.cache_dir)

    results = engine.run(
        tickers=tickers,
        screener=strategy,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        sma_periods=config.indicators.sma,
        rsi_periods=config.indicators.rsi,
        macd_config=config.indicators.macd,
    )

    # Rank by score (e.g. volatility) when the strategy provides one, high to low.
    if any(isinstance(r.get("score"), (int, float)) for r in results):
        results.sort(key=lambda r: r.get("score") or float("-inf"), reverse=True)

    print("\n" + format_results_table(results))

    if args.output:
        export_csv(results, args.output)
        logging.info("Results exported to %s", args.output)


if __name__ == "__main__":
    main()
