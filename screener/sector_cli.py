from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from prettytable import PrettyTable

from screener.config import ScreenConfig
from screener.data.sectors import sector_names
from screener.screeners.sector_rotation import compare_sector_peers, compute_sector_rotation


def _cell(v):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:+.1f}" if abs(v) < 1000 else f"{v:.0f}"
    return v


def _print_rotation(df):
    if df.empty:
        print("No sector data available.")
        return
    table = PrettyTable()
    table.field_names = ["Sector", "ETF", "Quadrant", "RS-Ratio", "RS-Mom",
                         "1M", "3M", "6M", "12M", "rel3M", "rel6M"]
    table.align = "r"
    table.align["Sector"] = "l"
    table.align["Quadrant"] = "l"
    for _, r in df.iterrows():
        table.add_row([
            r["sector"], r["etf"], r["quadrant"],
            _cell(r["rs_ratio"]), _cell(r["rs_momentum"]),
            _cell(r["ret_1m"]), _cell(r["ret_3m"]), _cell(r["ret_6m"]), _cell(r["ret_12m"]),
            _cell(r["rel_3m"]), _cell(r["rel_6m"]),
        ])
    table.title = "Sector Rotation (returns %, rel = vs SPY; sorted by 3M relative)"
    print(table.get_string())
    print("\nQuadrant guide: Leading=strong  Weakening=fading  Lagging=weak  Improving=turning up")


def _print_peers(df, sector_label):
    if df.empty:
        print(f"No peer data for sector '{sector_label}'.")
        return
    etf = df.attrs.get("etf", "?")
    sret = df.attrs.get("sector_return")
    mret = df.attrs.get("market_return")
    wd = df.attrs.get("window_days")
    header = (
        f"Sector {df.attrs.get('sector', sector_label)} ({etf}) over ~{wd} bars | "
        f"sector {etf}={_cell(sret)}%  market SPY={_cell(mret)}%"
    )
    table = PrettyTable()
    table.field_names = ["Ticker", "Name", "Last", "Return", "vs Sector", "vs Market", "Beats ETF"]
    table.align = "r"
    table.align["Ticker"] = "l"
    table.align["Name"] = "l"
    for _, r in df.iterrows():
        table.add_row([
            r["ticker"], (r["name"] or "")[:26], _cell(r["last_price"]),
            _cell(r["return"]), _cell(r["rel_sector"]), _cell(r["rel_market"]),
            "yes" if r["beats_sector"] else "",
        ])
    table.title = header
    print(table.get_string())


def main():
    parser = argparse.ArgumentParser(description="Sector rotation & peer comparison")
    parser.add_argument("mode", choices=["rotation", "peers"],
                        help="'rotation' = all sectors vs market; 'peers' = stocks within one sector")
    parser.add_argument("--sector", type=str, default=None,
                        help="Sector name/alias/ETF (required for 'peers'). e.g. 'tech', 'Energy', 'XLF'")
    parser.add_argument("--config", "-c", type=str, default="config.yaml")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--interval", type=str, default=None, help="Data interval (1d, 1h, ...)")
    parser.add_argument("--window", type=int, default=63,
                        help="Comparison window in bars (peers) / RRG smoothing window (rotation)")
    parser.add_argument("--max-names", type=int, default=None,
                        help="Limit constituents scanned in 'peers' mode")
    parser.add_argument("--output", "-o", type=str, default=None, help="Optional CSV output path")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s | %(name)s | %(message)s",
    )

    config = ScreenConfig.from_yaml(args.config)
    start = args.start or config.start_date
    end = args.end or config.end_date
    interval = args.interval or config.interval

    if args.mode == "rotation":
        df = compute_sector_rotation(start, end, interval=interval,
                                     rrg_window=args.window, cache_dir=config.cache_dir)
        print()
        _print_rotation(df)
    else:
        if not args.sector:
            parser.error("--sector is required for 'peers' mode. "
                         f"Choices include: {', '.join(sector_names())}")
        df = compare_sector_peers(args.sector, start, end, interval=interval,
                                  window_days=args.window, cache_dir=config.cache_dir,
                                  max_names=args.max_names)
        print()
        _print_peers(df, args.sector)

    if args.output and not df.empty:
        df.to_csv(args.output, index=False)
        print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
