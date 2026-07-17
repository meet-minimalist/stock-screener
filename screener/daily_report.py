from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
from prettytable import PrettyTable
from tqdm import tqdm

from screener.config import ScreenConfig
from screener.data.fetcher import DataFetcher
from screener.data.sectors import load_constituents
from screener.data.universe import get_ticker_list
from screener.fundamentals import get_fundamentals
from screener.markets import get_market
from screener.indicators.calculator import IndicatorCalculator
from screener.scoring import ConvictionScorer
from screener.screeners.sector_rotation import compute_sector_rotation
from screener.signals import compute_signals

logger = logging.getLogger(__name__)

_MACD = {"fast": 12, "slow": 26, "signal": 9}


def run_daily(
    start_date: str,
    end_date: str,
    interval: str = "1d",
    universe: str = "sp500",
    top_n: int = 15,
    cache_dir: str = "data/yfinance_cache",
    market: str = "us",
    show_progress: bool = True,
) -> dict:
    """Run the full daily pipeline and return the ranked candidates + context."""
    mkt = get_market(market)

    # 1) Sector context (RRG quadrant + returns per sector) — computed once.
    # A benchmark/data hiccup (e.g. Yahoo rate-limiting) must not sink the whole
    # run: fall back to no sector context so the page still builds.
    try:
        rotation = compute_sector_rotation(start_date, end_date, interval=interval,
                                           cache_dir=cache_dir, market=mkt)
    except Exception as exc:
        logger.warning("Sector rotation unavailable for %s (%s); continuing without it",
                       mkt.key, exc)
        rotation = pd.DataFrame()
    sector_ctx = {
        row["sector"]: {"quadrant": row["quadrant"], "etf": row["etf"],
                        "ret_3m": row["ret_3m"], "ret_6m": row["ret_6m"]}
        for _, row in rotation.iterrows()
    }

    # 2) Universe first — this also caches the constituent files the sector map reads.
    tickers = get_ticker_list(universe)

    # 3) Ticker -> sector map (GICS for US, NSE Industry for India).
    constituents = load_constituents(market=mkt.key)
    sec_map = dict(zip(constituents["Symbol"], constituents["sector"]))

    # 4) Fundamentals from the latest committed snapshot (empty if never refreshed).
    funds = get_fundamentals(mkt.key, tickers)

    fetcher = DataFetcher(cache_dir=cache_dir)
    calc = IndicatorCalculator()
    scorer = ConvictionScorer()

    scored: list[dict] = []
    filtered = 0
    iterator = tqdm(tickers, desc="Scoring", unit="ticker") if show_progress else tickers
    for ticker in iterator:
        # Records key by the bare symbol; prices use the market's yfinance suffix.
        df = fetcher.get_data(ticker + mkt.ticker_suffix, start_date, end_date, interval=interval)
        if df.empty:
            continue
        df = calc.compute(df, sma_periods=[20, 50, 200], rsi_periods=[14],
                          macd_config=_MACD)
        res = scorer.score(ticker, sec_map.get(ticker), df, sector_ctx,
                           fund=funds.get(ticker))
        if res is None:
            continue
        if res.score is None:  # gated (liquidity or fundamental)
            filtered += 1
            continue
        res.signals, res.signal_notes = compute_signals(ticker, df)  # screen membership + why
        scored.append(res)

    ranked = sorted(scored, key=lambda r: r.score, reverse=True)
    leaders = [r["sector"] for _, r in rotation.iterrows()
               if r["quadrant"] in ("Leading", "Improving")]

    return {
        "as_of": end_date,
        "universe": universe,
        "market": mkt.key,
        "market_label": mkt.label,
        "currency": mkt.currency,
        "scanned": len(tickers),
        "scored": len(scored),
        "filtered_out": filtered,
        "leading_sectors": leaders[:5],
        "rotation": rotation,
        "records": ranked,       # all passing StockRecords (for the screen tabs)
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
                         "3M", "12M", "P/E", "ROE", "Why"]
    table.align = "r"
    table.align["Ticker"] = "l"
    table.align["Sector"] = "l"
    table.align["Why"] = "l"
    for i, r in enumerate(result["top"], 1):
        table.add_row([
            i, r.ticker, r.score, r.price,
            (r.sector or "?")[:16], r.daily_vol,
            _fmt(r.ret_3m), _fmt(r.ret_12m),
            _plain(r.pe), _pct(r.roe), r.reason[:52],
        ])
    lines.append(table.get_string())
    return "\n".join(lines)


def _fmt(v) -> str:
    return f"{v:+.0f}" if isinstance(v, (int, float)) else "n/a"


def _plain(v) -> str:
    return f"{v:.1f}" if isinstance(v, (int, float)) else "-"


def _pct(v) -> str:
    return f"{v:.0f}%" if isinstance(v, (int, float)) else "-"


def main():
    parser = argparse.ArgumentParser(description="Daily conviction-ranked stock picks")
    parser.add_argument("--config", "-c", type=str, default="config.yaml")
    parser.add_argument("--market", "-m", type=str, default="us", help="Market: us or in")
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
    mkt = get_market(args.market)
    result = run_daily(
        start_date=start,
        end_date=end,
        interval=interval,
        universe=args.universe or mkt.universe,
        top_n=args.top,
        cache_dir=config.cache_dir,
        market=mkt.key,
    )

    report = format_report(result)
    print("\n" + report)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\nSaved report to {args.output}")

    if args.html:
        from screener.web import build_site, render_rrg_data_uri
        uri = render_rrg_data_uri(start, end, interval, cache_dir=config.cache_dir,
                                  market=mkt.key)
        page = build_site(result, uri)
        Path(args.html).parent.mkdir(parents=True, exist_ok=True)
        Path(args.html).write_text(page, encoding="utf-8")
        print(f"Saved HTML site to {args.html}")


if __name__ == "__main__":
    main()
