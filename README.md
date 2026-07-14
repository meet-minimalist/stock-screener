# stock-screener

A technical stock screener for US equities (S&P 500) with a command-line
interface, a Streamlit web UI, and a sector-rotation view. It screens a ticker
universe against a library of technical strategies, ranks candidates, and shows
annotated price charts — plus a Relative Rotation Graph (RRG) for spotting which
sectors are leading, lagging, or turning.

Price data is pulled from Yahoo Finance and cached on disk, so repeated scans are
fast after the first run.

## Features

- **Technical screeners** — RSI oversold bounce, bullish MACD, golden cross,
  near 52-week high, big single-day gain, high volume, candlestick patterns.
- **Volatile Uptrend ranking** — ranks stocks by daily-return volatility and
  flags names that are *already trending up* (positive 3M/6M/12M returns) while
  still being volatile enough to trade.
- **Sector rotation (RRG)** — classifies every GICS sector (via its SPDR ETF)
  vs SPY into Leading / Weakening / Lagging / Improving, with a scatter plot and
  historical tails.
- **Sector peer comparison** — ranks the stocks in one sector against each other
  and against the sector ETF and the market.
- **Two front-ends** — a CLI for scripted runs and a Streamlit app for
  interactive exploration with charts.

## Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.10+. `TA-Lib` needs its native library installed; on Windows the
prebuilt wheel usually suffices. Price data uses
[`yf-cache`](https://github.com/meet-minimalist/yf_cache) over `yfinance`.

## Configuration

Defaults live in `config.yaml` (universe, date range, interval, cache location,
and indicator parameters). Any value can be overridden with CLI flags.

```yaml
universe: sp500
start_date: "2025-06-22"
end_date: "2026-06-22"
interval: "1d"
cache_dir: "data/yfinance_cache"
```

## Usage

### CLI screener

```bash
# Oversold RSI bounce across the S&P 500
python -m screener.cli --strategy oversold_bounce

# Rank volatile uptrends (needs ~2 years of history for the 2Y return)
python -m screener.cli --strategy volatile_uptrend --start 2024-06-22 --end 2026-06-22

# Custom ticker list, export results to CSV
python -m screener.cli --strategy golden_cross --universe my_tickers.csv -o out.csv
```

Available strategies: `oversold_bounce`, `bullish_macd`, `golden_cross`,
`near_52w_high`, `big_gain`, `high_volume`, `candle_patterns`, `volatile_uptrend`.

Common flags: `--universe` (`sp500` or a CSV path), `--start` / `--end`,
`--interval`, `--output`, `--verbose`.

### Sector rotation & peers CLI

```bash
# All sectors vs the market, classified into RRG quadrants
python -m screener.sector_cli rotation --start 2024-06-22 --end 2026-06-22

# Rank the stocks in one sector vs each other and the sector ETF
python -m screener.sector_cli peers --sector tech --max-names 25
```

`--sector` accepts a GICS name (`"Health Care"`), an alias (`tech`, `finance`),
or the ETF ticker (`XLF`).

### Streamlit app

```bash
streamlit run screener/app.py
```

Opens at http://localhost:8501 with two tabs:

- **📊 Screener** — pick a universe, strategy, date range, and interval; run a
  scan; browse the ranked results and an annotated Plotly chart per ticker.
- **🔄 Sector Rotation** — a Relative Rotation Graph of all sectors vs SPY.

## Understanding the Relative Rotation Graph

Each sector's SPDR ETF is measured against SPY:

- **RS-Ratio** (x-axis) — the sector's relative strength vs its own recent trend.
  Above 100 = outperforming the market; below = underperforming.
- **RS-Momentum** (y-axis) — whether that relative strength is building or fading.

The two axes form four quadrants that a sector rotates through, clockwise:

| Quadrant | RS-Ratio | RS-Momentum | Meaning |
|----------|----------|-------------|---------|
| **Leading** | > 100 | > 100 | Strong and strengthening (bullish) |
| **Weakening** | > 100 | < 100 | Strong but losing momentum (take profits) |
| **Lagging** | < 100 | < 100 | Weak and still falling (avoid) |
| **Improving** | < 100 | > 100 | Weak but turning up (early accumulation) |

In the app, each sector is drawn as a **comet tail** of weekly positions ending in
a labelled head — so you can see where a sector was 3–6 months ago and where it is
now. The RS-Ratio/Momentum values are a transparent approximation of the
proprietary JdK RRG method — good enough to classify and rank consistently.

## Project layout

```
screener/
  cli.py                 # CLI entry point for the technical screeners
  sector_cli.py          # CLI entry point for rotation / peers
  app.py                 # Streamlit UI
  config.py              # YAML config loader
  data/
    fetcher.py           # cached yfinance downloader
    universe.py          # S&P 500 / custom ticker lists
    sectors.py           # GICS sector -> SPDR ETF map + constituents
  indicators/
    calculator.py        # SMA / RSI / MACD
  screeners/
    base.py, engine.py   # Screener contract + scanning engine
    strategies.py        # the technical strategies
    sector_rotation.py   # RRG math, sector rotation & peer comparison
  reports/
    formatter.py         # results table + CSV export
    chart_markers.py     # annotated price charts
    rrg_chart.py         # Relative Rotation Graph
```

## Notes

- The local price cache (`data/yfinance_cache/`) and uploads (`data/uploads/`)
  are gitignored; they are rebuilt on demand.
- The Yahoo downloader is occasionally flaky on the first request for a ticker —
  if a scan reports "no data" for something you expect, just run it again.
