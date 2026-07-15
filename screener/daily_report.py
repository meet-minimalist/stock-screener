from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from prettytable import PrettyTable
from tqdm import tqdm

from screener.config import ScreenConfig
from screener.data.fetcher import DataFetcher
from screener.data.sectors import load_constituents
from screener.data.universe import get_ticker_list
from screener.indicators.calculator import IndicatorCalculator
from screener.scoring import ConvictionScorer
from screener.screeners.sector_rotation import compute_sector_rotation

logger = logging.getLogger(__name__)

_MACD = {"fast": 12, "slow": 26, "signal": 9}


def run_daily(
    start_date: str,
    end_date: str,
    interval: str = "1d",
    universe: str = "sp500",
    top_n: int = 15,
    cache_dir: str = "data/yfinance_cache",
    show_progress: bool = True,
) -> dict:
    """Run the full daily pipeline and return the ranked candidates + context."""
    # 1) Sector context (RRG quadrant + returns per sector) — computed once.
    rotation = compute_sector_rotation(start_date, end_date, interval=interval,
                                       cache_dir=cache_dir)
    sector_ctx = {
        row["sector"]: {"quadrant": row["quadrant"], "etf": row["etf"],
                        "ret_3m": row["ret_3m"], "ret_6m": row["ret_6m"]}
        for _, row in rotation.iterrows()
    }

    # 2) Ticker -> GICS sector map.
    constituents = load_constituents()
    sec_map = dict(zip(constituents["Symbol"], constituents["GICS Sector"]))

    tickers = get_ticker_list(universe)
    fetcher = DataFetcher(cache_dir=cache_dir)
    calc = IndicatorCalculator()
    scorer = ConvictionScorer()

    scored: list[dict] = []
    filtered = 0
    iterator = tqdm(tickers, desc="Scoring", unit="ticker") if show_progress else tickers
    for ticker in iterator:
        df = fetcher.get_data(ticker, start_date, end_date, interval=interval)
        if df.empty:
            continue
        df = calc.compute(df, sma_periods=[50, 200], macd_config=_MACD)
        res = scorer.score(ticker, sec_map.get(ticker), df, sector_ctx)
        if res is None:
            continue
        if not res.get("liquidity_ok"):
            filtered += 1
            continue
        scored.append(res)

    ranked = sorted(scored, key=lambda r: r["score"], reverse=True)
    leaders = [r["sector"] for _, r in rotation.iterrows()
               if r["quadrant"] in ("Leading", "Improving")]

    return {
        "as_of": end_date,
        "universe": universe,
        "scanned": len(tickers),
        "scored": len(scored),
        "filtered_out": filtered,
        "leading_sectors": leaders[:5],
        "rotation": rotation,
        "ranked": ranked,
        "top": ranked[:top_n],
    }


def format_report(result: dict) -> str:
    """Console/markdown-ish text report of the day's picks."""
    lines = [
        f"Daily Conviction Report — as of {result['as_of']}",
        f"Universe: {result['universe']}  |  scored {result['scored']} "
        f"(filtered {result['filtered_out']}) of {result['scanned']}",
    ]
    if result["leading_sectors"]:
        lines.append("Sector tailwinds (Leading/Improving): "
                     + ", ".join(result["leading_sectors"]))
    lines.append("")

    table = PrettyTable()
    table.field_names = ["#", "Ticker", "Score", "Price", "Sector", "Vol%",
                         "3M", "12M", "Why"]
    table.align = "r"
    table.align["Ticker"] = "l"
    table.align["Sector"] = "l"
    table.align["Why"] = "l"
    for i, r in enumerate(result["top"], 1):
        table.add_row([
            i, r["ticker"], r["score"], r["price"],
            (r["sector"] or "?")[:16], r["daily_vol"],
            _fmt(r["ret_3m"]), _fmt(r["ret_12m"]), r["reason"][:60],
        ])
    lines.append(table.get_string())
    return "\n".join(lines)


def _fmt(v) -> str:
    return f"{v:+.0f}" if isinstance(v, (int, float)) else "n/a"


def main():
    parser = argparse.ArgumentParser(description="Daily conviction-ranked stock picks")
    parser.add_argument("--config", "-c", type=str, default="config.yaml")
    parser.add_argument("--universe", "-u", type=str, default=None)
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--interval", type=str, default=None)
    parser.add_argument("--top", type=int, default=15, help="How many picks to show")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Write the report text to this file")
    parser.add_argument("--html", type=str, default=None,
                        help="Write a standalone HTML dashboard to this path (GitHub Pages)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    try:  # keep em-dash / middot readable on Windows consoles
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s | %(name)s | %(message)s",
    )

    config = ScreenConfig.from_yaml(args.config)
    start = args.start or config.start_date
    end = args.end or config.end_date
    interval = args.interval or config.interval
    result = run_daily(
        start_date=start,
        end_date=end,
        interval=interval,
        universe=args.universe or config.universe,
        top_n=args.top,
        cache_dir=config.cache_dir,
    )

    report = format_report(result)
    print("\n" + report)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\nSaved report to {args.output}")

    if args.html:
        from screener.report_html import build_dashboard_body, render_rrg_data_uri, wrap_page
        uri = render_rrg_data_uri(start, end, interval, cache_dir=config.cache_dir)
        page = wrap_page(build_dashboard_body(result, uri))
        Path(args.html).parent.mkdir(parents=True, exist_ok=True)
        Path(args.html).write_text(page, encoding="utf-8")
        print(f"Saved HTML dashboard to {args.html}")


if __name__ == "__main__":
    main()
