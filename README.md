# stock-screener

A stock screener and daily selection tool for the **US (S&P 1500)** and **India
(Nifty Total Market)**. It blends technicals, sector rotation, and fundamentals
into a single **Daily Conviction Score**, publishes a hands-off **interactive
dashboard** to GitHub Pages every trading day, and also offers a CLI and a
Streamlit app for interactive work.

Price data is pulled from Yahoo Finance and cached on disk; fundamentals come from
finviz (US) and screener.in (India) and are snapshotted over time. Repeated scans
are fast after the first run.

Each market is a [`Market`](screener/markets.py) config (benchmark, sector indices,
universe, currency, fundamentals source), so the same pipeline runs both.

## Features

- **Daily Conviction Score** — one 0–100 ranking per stock, blending a sector
  RRG tailwind, trend strength, relative strength vs its own sector, tradeable
  volatility, a fresh daily trigger, and fundamentals, behind liquidity and
  fundamental gates. See [`scoring.py`](screener/scoring.py).
- **Fundamental analysis** — value, quality, and growth metrics used as a gate, a
  scored factor, and displayed columns, plus a dedicated A–F **fundamental
  screener**. US via finviz (bulk); India via the private
  [`screener-in-fetcher`](https://github.com/meet-minimalist/screener.in-fetcher)
  screener.in module. Snapshots accumulate under `data/fundamentals/<market>/`.
- **Two markets** — US (S&P 1500) and India (Nifty Total Market, `.NS` prices,
  NSE Industry sectors, Nifty sector-index RRG). Cross-linked pages: `/`,
  `/fundamentals/`, `/in/`, `/in/fundamentals/`.
- **Interactive multi-tab screener** — a ChartMill-style hosted page: every
  screen (Top Picks, Volatile Uptrends, 52-week-high breakouts, Sector Leaders,
  Value + Momentum, Quality Compounders, candlestick patterns, …) is a sortable,
  filterable, searchable table with CSV export and rating badges.
- **Technical screeners** — RSI oversold bounce, bullish MACD, golden cross,
  near 52-week high, big single-day gain, high volume, candlestick patterns.
- **Sector rotation (RRG)** — classifies every GICS sector (via its SPDR ETF)
  vs SPY into Leading / Weakening / Lagging / Improving, with a scatter plot and
  historical tails; plus a sector peer comparison.
- **Automated & hands-off** — a GitHub Action rebuilds and deploys the dashboard
  after each US close; a weekly Action refreshes the fundamentals snapshot.

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

### Daily conviction report & interactive site

```bash
# US (default market). Console table of the top-ranked names.
python -m screener.daily_report --start 2024-06-22 --end 2026-06-22 --top 20

# India: full Nifty pipeline (.NS prices, Nifty RRG), interactive page
python -m screener.daily_report --market in --universe nifty_total \
  --start 2024-06-22 --end 2026-06-22 --html site/in/index.html
```

The pipeline computes sector context, scores every constituent, tags each with the
screens it belongs to, and (with `--html`) writes a self-contained page with a tab
per screen, the sector RRG, and sortable/filterable/searchable tables.

### Streamlit app

```bash
streamlit run screener/app.py
```

Opens at http://localhost:8501 with two tabs:

- **📊 Screener** — pick a universe, strategy, date range, and interval; run a
  scan; browse the ranked results and an annotated Plotly chart per ticker.
- **🔄 Sector Rotation** — a Relative Rotation Graph of all sectors vs SPY.

## Fundamentals

Both sources normalise into one schema ([`screener/fundamentals/`](screener/fundamentals/)),
so grading and the screener are shared:

```bash
python -m screener.fundamentals --market us      # finviz  -> data/fundamentals/us/
python -m screener.fundamentals --market in      # screener.in -> data/fundamentals/in/
```

Each refresh writes a dated snapshot **and** a `latest.csv` per market — the sites
keep no history, so these snapshots become our own accumulating dataset. The daily
run only reads the committed `latest.csv` (it never scrapes), so a missing snapshot
just leaves the fundamental factor neutral. India uses the **private**
`screener-in-fetcher` module; optional screener.in login via `SCREENER_EMAIL` /
`SCREENER_PASSWORD`.

## Automated daily publishing (GitHub Actions → Pages)

Enable Pages once via **Settings → Pages → Build and deployment → Source: GitHub
Actions** (needs a public repo, or a paid plan for private). Three workflows:

- **`daily-picks.yml`** — after each market close, builds all four pages (US +
  India, daily + fundamentals) into one site and deploys to
  `https://<user>.github.io/stock-screener/`. A single deploy because Pages serves
  one site.
- **`fundamentals-refresh.yml`** — weekly finviz (US) snapshot, committed back.
- **`india-fundamentals.yml`** — weekly screener.in (India) snapshot, committed
  back. Installs the private module, so it needs a **`GH_PAT`** repo secret whose
  token has **read access to `screener.in-fetcher`** (a fine-grained token scoped
  to that repo, Contents: Read).

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
  cli.py                 # CLI for the technical screeners
  sector_cli.py          # CLI for rotation / peers
  daily_report.py        # daily pipeline: score universe -> report / site
  app.py                 # Streamlit UI
  config.py              # YAML config loader
  paths.py               # single source of truth for data/ locations
  scoring.py             # ConvictionScorer: the composite score + gates
  records.py             # StockRecord domain model
  screens.py             # registry of browsable screens (one entry per tab)
  signals.py             # runs the strategies, returns per-stock signals + notes
  data/
    fetcher.py           # cached yfinance downloader
    universe.py          # S&P 500 / custom ticker lists
    sectors.py           # GICS sector -> SPDR ETF map + constituents
  fundamentals/          # finviz source, snapshot store, service
  indicators/
    calculator.py        # SMA / RSI / MACD
  screeners/
    base.py, engine.py   # Screener contract + scanning engine
    strategies.py        # the technical strategies
    sector_rotation.py   # RRG math, sector rotation & peer comparison
  reports/               # console table + Plotly charts (RRG, markers)
  web/                   # the interactive site: charts, assets (CSS/JS), site
tests/                   # pytest unit tests (scoring, screens, fundamentals)
```

Everything the app downloads lives under `data/` (see `screener/paths.py`):
`yfinance_cache/` (prices) and `uploads/` are gitignored; `tickers/` and
`fundamentals/` are committed.

## Notes

- Run the tests with `pytest`.
- The local price cache (`data/yfinance_cache/`) and uploads are gitignored and
  rebuilt on demand.
- The Yahoo downloader is occasionally flaky on the first request for a ticker —
  if a scan reports "no data" for something you expect, just run it again.
- The US universe is the S&P 500 (large-cap) for now; broader coverage and an
  India (Nifty) view are planned.
