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
from screener.markets import cap_classifier, get_market
from screener.indicators.calculator import IndicatorCalculator
from screener.scoring import ConvictionScorer, Gates
from screener.records import StockRecord
from screener.screeners.dual_momentum_rotation import (
    SIGNAL_KEY as DUAL_MOMENTUM_KEY,
    UNIVERSE as DUAL_MOMENTUM_UNIVERSE,
    compute_metrics as compute_dual_momentum,
)
from screener.screeners.momentum_portfolio import TRAIL_PCT as _MS_TRAIL, simulate as _simulate_midsmall

# Signal keys for the MidSmallcap portfolio views (India). Held/sold-today reuse the
# rotation key (BUY/SELL); recently-sold and rebuy get their own so they tab separately.
DUAL_RECENT_KEY = "dual_momentum_recent"
DUAL_REBUY_KEY = "dual_momentum_rebuy"
from screener.screeners.momentum_rotation import (
    SIGNAL_KEY as MOMENTUM_ROTATION_KEY,
    assign_signals as assign_rotation_signals,
    compute_metrics as compute_momentum,
)
from screener.screeners.sector_rotation import compute_sector_rotation
from screener.signals import compute_signals

logger = logging.getLogger(__name__)

# Trailing bar older than this (calendar days) behind the run's freshest bar counts as
# a stale fetch -- the signature of a rate-limited run that served old cached months.
_STALE_DAYS = 6


class _DropMissingMonthNoise(logging.Filter):
    """Silence yf_cache's benign per-month "Data doesn't exist" lines (emitted for
    every pre-listing month of a new listing) while letting rate-limit lines through."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        return "Data doesn't exist" not in record.getMessage()

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
    include_bse: bool = True,
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

    # 3) Ticker -> sector map (GICS for US, NSE Industry for India) and the yfinance
    # price symbol per ticker (the market suffix — ``.NS`` for NSE — by default).
    constituents = load_constituents(market=mkt.key)
    sec_map = dict(zip(constituents["Symbol"], constituents["sector"]))
    price_sym = {t: t + mkt.ticker_suffix for t in tickers}

    # India SME is priced with a mix of ``.NS`` (NSE Emerge) and ``.BO`` (BSE SME)
    # symbols, resolved explicitly from the SME universe rather than a single suffix.
    if mkt.key == "in_sme":
        from screener.data.sme import sme_price_universe
        _sme_t, _sme_sec, sme_price = sme_price_universe()
        price_sym = {t: sme_price.get(t, t + mkt.ticker_suffix) for t in tickers}

    # Fold in BSE-exclusive names, priced via their ``.BO`` yfinance symbols. The
    # scorer's liquidity gate drops the illiquid ones, so only tradeable names score.
    if mkt.key == "in" and include_bse:
        from screener.data.bse import india_extra_price_universe
        bse_tickers, bse_sectors, bse_price = india_extra_price_universe()
        added = 0
        for t in bse_tickers:
            if t not in price_sym:                # keep NSE on any symbol clash
                tickers.append(t)
                price_sym[t] = bse_price[t]
                sec_map.setdefault(t, bse_sectors.get(t))
                added += 1
        if added:
            logger.info("Added %d BSE-exclusive names to the India price universe", added)

    # 4) Fundamentals from the latest committed snapshot (empty if never refreshed).
    funds = get_fundamentals(mkt.key, tickers)

    fetcher = DataFetcher(cache_dir=cache_dir)
    calc = IndicatorCalculator()
    # SME turnover is structurally low, so the mainboard ₹50 lakh/day gate would empty
    # the page; relax it to ₹10 lakh/day so genuinely dead names still drop out.
    # soft_fundamental: keep richly-valued/levered names in the results (scored, but
    # flagged) so the page's gate toggles can reveal them -- a breakout screen should be
    # able to show a high-P/E leader. The liquidity gate stays hard.
    scorer = (ConvictionScorer(gates=Gates(min_dollar_vol=1_000_000.0, min_price=5.0),
                               soft_fundamental=True)
              if mkt.key == "in_sme"
              else ConvictionScorer(soft_fundamental=True))

    scored: list[dict] = []
    filtered = 0
    empty = 0                                 # price fetch returned no data at all
    fetch_last: list = []                     # last bar date per non-empty fetch (staleness)
    # Momentum for the cross-sectional rotation signal is a *market-specific* strategy:
    # quad-horizon over the whole US universe, dual-horizon over the NIFTY MidSmallcap
    # 400 for India. Collect it for every stock with enough history (not just the
    # gate-passers) so the ranking pass below sees the full universe.
    compute_mom = {"us": compute_momentum, "in": compute_dual_momentum}.get(mkt.key)
    momentum_metrics: dict = {}
    # For India, keep the raw close of every NIFTY MidSmallcap 400 member so the
    # portfolio simulator can replay the strategy (entry prices, stops, cooldowns).
    members: set[str] = set()
    member_closes: dict = {}
    if mkt.key == "in":
        try:
            members = set(get_ticker_list(DUAL_MOMENTUM_UNIVERSE))
        except Exception as exc:  # noqa: BLE001 - optional screens, never fatal
            logger.warning("MidSmallcap 400 list unavailable (%s); skipping its screens", exc)
    iterator = tqdm(tickers, desc="Scoring", unit="ticker") if show_progress else tickers
    for ticker in iterator:
        # Records key by the bare symbol; prices use its resolved yfinance symbol
        # (``.NS`` for NSE, ``.BO`` for BSE-exclusive names).
        df = fetcher.get_data(price_sym[ticker], start_date, end_date, interval=interval)
        if df.empty:
            empty += 1
            continue
        try:
            fetch_last.append(df.index[-1])
        except (IndexError, AttributeError):
            pass
        df = calc.compute(df, sma_periods=[20, 50, 200], rsi_periods=[14],
                          macd_config=_MACD)
        if compute_mom is not None:
            mm = compute_mom(df)
            if mm is not None:
                momentum_metrics[ticker] = mm
        if ticker in members:
            member_closes[ticker] = df["Close"]
        res = scorer.score(ticker, sec_map.get(ticker), df, sector_ctx,
                           fund=funds.get(ticker))
        if res is None:
            continue
        if res.score is None:  # gated (liquidity or fundamental)
            filtered += 1
            continue
        res.signals, res.signal_notes = compute_signals(ticker, df)  # screen membership + why
        scored.append(res)

    # Momentum score (display) for every gate-passing record.
    for res in scored:
        mm = momentum_metrics.get(res.ticker)
        if mm is not None:
            res.momentum = round(mm.momentum, 4)

    # Market-specific momentum signals. US: stateless quad-horizon rotation. India:
    # a virtual-portfolio replay of the MidSmallcap strategy (held/sold/rebuy with
    # entry prices + stops), which can surface names the liquidity gate dropped, so
    # those get lightweight synthesised records appended below.
    extra_records: list[StockRecord] = []
    if mkt.key == "us":
        rotation_signals = assign_rotation_signals(momentum_metrics)
        for res in scored:
            sig = rotation_signals.get(res.ticker)
            if sig:
                res.signals[MOMENTUM_ROTATION_KEY] = sig
    elif mkt.key == "in" and member_closes:
        extra_records = _attach_midsmall_portfolio(scored, member_closes, sec_map,
                                                   momentum_metrics)

    # Size segment (Mega/Large/Mid/Small/Micro) so thin small/micro-caps are labelled
    # rather than looking like blue chips. India ranks the fetched universe (SEBI-style).
    classify = cap_classifier(mkt, [getattr(f, "market_cap", None) for f in funds.values()])
    for res in scored:
        res.cap_tier = classify(res.market_cap)

    # Staleness: rate-limited runs serve old cached months, so the trailing bar lags the
    # run's freshest bar. A run where many names are stale is degraded even with 0 empties.
    stale = 0
    if fetch_last:
        fresh = max(fetch_last)
        stale = sum(1 for d in fetch_last if (fresh - d).days > _STALE_DAYS)

    ranked = sorted(scored, key=lambda r: r.score, reverse=True)
    records = ranked + extra_records          # extra = MidSmallcap names below the gate
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
        "empty_fetches": empty,
        "stale_fetches": stale,
        "leading_sectors": leaders[:5],
        "rotation": rotation,
        "records": records,      # passing StockRecords + MidSmallcap portfolio names
        "ranked": ranked,
        "top": ranked[:top_n],
    }


def _attach_midsmall_portfolio(scored: list, member_closes: dict, sec_map: dict,
                               momentum_metrics: dict) -> list:
    """Replay the MidSmallcap strategy and stamp held/sold/rebuy state onto records.

    Enriches the matching scored record where present; otherwise synthesises a minimal
    record (score ``None`` so it only surfaces in the MidSmallcap tabs, never the
    conviction screens) for names the liquidity gate dropped. Returns the synthesised
    records to append to the page's record list.
    """
    pf = _simulate_midsmall(member_closes)
    by_ticker = {r.ticker: r for r in scored}
    extra: list = []

    def rec_for(ticker: str, price: float | None):
        r = by_ticker.get(ticker)
        if r is None:
            r = StockRecord(ticker=ticker, sector=sec_map.get(ticker),
                            price=round(price, 2) if price is not None else None)
            mm = momentum_metrics.get(ticker)
            if mm is not None:
                r.momentum = round(mm.momentum, 4)
            by_ticker[ticker] = r
            extra.append(r)
        return r

    for h in pf.held:                              # currently held -> BUY list, with stop
        r = rec_for(h.ticker, h.current_price)
        r.signals[DUAL_MOMENTUM_KEY] = "BUY"
        r.entry_price, r.stop_loss, r.pl_pct = h.entry_price, h.stop_loss, h.gain_pct
        r.entry_date, r.days_held = h.entry_date, h.days_held
        if r.price is None:
            r.price = h.current_price

    for s in pf.sold:                              # exited: today -> SELL, older -> recent
        r = rec_for(s.ticker, s.exit_price)
        r.signals[DUAL_MOMENTUM_KEY if s.days_ago == 0 else DUAL_RECENT_KEY] = "SELL"
        r.entry_price, r.pl_pct = s.entry_price, s.gain_pct
        r.entry_date = s.entry_date
        r.exit_reason, r.days_ago = s.reason, s.days_ago
        if r.price is None:
            r.price = s.exit_price

    for rb in pf.rebuys:                           # off cooldown, re-qualified -> rebuy
        r = rec_for(rb.ticker, rb.current_price)
        r.signals[DUAL_REBUY_KEY] = "BUY"
        r.entry_price = rb.prev_entry_price        # earlier entry, for reference
        r.stop_loss = round(rb.current_price * (1.0 - _MS_TRAIL), 2)
        if r.price is None:
            r.price = rb.current_price

    return extra


def empty_fetch_rate(result: dict) -> float:
    """Share of the scanned universe whose price fetch returned no data at all.

    A normal run is a few percent (genuinely delisted names). A spike means Yahoo
    rate-limited the run, so good names are silently missing -- the signal the deploy
    gate uses to refuse overwriting the last good build.
    """
    scanned = result.get("scanned") or 0
    if not scanned:
        return 0.0
    return result.get("empty_fetches", 0) / scanned


def degraded_fetch_rate(result: dict) -> float:
    """Share of the universe with no data OR stale (old cached) data.

    Broader than the empty rate: a rate-limited run returns stale-but-nonempty frames,
    which the empty rate misses. This is what the deploy gate acts on.
    """
    scanned = result.get("scanned") or 0
    if not scanned:
        return 0.0
    return (result.get("empty_fetches", 0) + result.get("stale_fetches", 0)) / scanned


def format_report(result: dict) -> str:
    """Console/markdown-ish text report of the day's picks."""
    lines = [
        f"Daily Conviction Report — as of {result['as_of']}",
        f"Universe: {result['universe']}  |  scored {result['scored']} "
        f"(filtered {result['filtered_out']}) of {result['scanned']}  |  "
        f"empty {result.get('empty_fetches', 0)} + stale {result.get('stale_fetches', 0)} "
        f"= degraded {degraded_fetch_rate(result):.1%}",
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
    parser.add_argument("--no-bse", action="store_true",
                        help="India only: exclude the BSE-exclusive names (NSE price universe only)")
    parser.add_argument("--max-empty-rate", type=float, default=0.25,
                        help="Exit non-zero (so CI skips deploy and keeps the last good "
                             "build) if the share of empty OR stale price fetches exceeds "
                             "this. Set to 1.0 to disable, e.g. for the thin SME universe.")
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
    if not args.verbose:
        # yfinance logs an ERROR per missing month for every dead/unlisted symbol
        # (e.g. MCCHRLS-B.NS emits a line per month of the window). The fetch layer
        # already handles empty results and the health gate tracks them, so keep that
        # non-actionable chatter out of the build log unless explicitly debugging.
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
        # yf_cache logs a benign "Data doesn't exist" per pre-listing month for every
        # newly-listed name -- drop those, but KEEP rate-limit lines visible, since a
        # throttled run is a real signal (and the staleness gate acts on its damage).
        logging.getLogger("yf_cache.downloader").addFilter(_DropMissingMonthNoise())

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
        include_bse=not args.no_bse,
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

    # Fetch-health gate. A rate-limited run silently drops good names (empty fetch) or
    # serves stale cached data; failing here makes CI skip the deploy so a degraded build
    # never overwrites the last good one.
    rate = degraded_fetch_rate(result)
    if rate > args.max_empty_rate:
        print(f"\nFETCH HEALTH GATE FAILED: {rate:.1%} of {result['scanned']} price "
              f"fetches were empty or stale (empty {result.get('empty_fetches', 0)}, "
              f"stale {result.get('stale_fetches', 0)}; limit {args.max_empty_rate:.0%}). "
              f"Refusing to publish a degraded build; keeping the last good deploy.")
        sys.exit(1)


if __name__ == "__main__":
    main()
