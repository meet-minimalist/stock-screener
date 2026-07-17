from __future__ import annotations

import html
import json
from typing import Any

from screener.screens import SCREENS, apply_screen
from screener.web.assets import SCRIPT, STYLE

# Column spec shared with the JS engine (assets.SCRIPT). type drives formatting
# and sortability; align "left" for text columns.
COLUMNS = [
    {"key": "rank", "label": "#", "type": "num", "sortable": False},
    {"key": "ticker", "label": "Ticker", "type": "text", "align": "left"},
    {"key": "score", "label": "Score", "type": "score"},
    {"key": "factors", "label": "Factors", "type": "factors", "sortable": False},
    {"key": "price", "label": "Price", "type": "money"},
    {"key": "sector", "label": "Sector", "type": "text", "align": "left"},
    {"key": "daily_vol", "label": "Vol%", "type": "num", "dp": 1},
    {"key": "ret_3m", "label": "3M", "type": "ret"},
    {"key": "ret_6m", "label": "6M", "type": "ret"},
    {"key": "ret_12m", "label": "12M", "type": "ret"},
    {"key": "rel_sector_3m", "label": "vs Sec", "type": "ret"},
    {"key": "pe", "label": "P/E", "type": "num", "dp": 1},
    {"key": "roe", "label": "ROE", "type": "pct"},
    {"key": "eps_growth", "label": "EPS gr", "type": "pct"},
    {"key": "debt_equity", "label": "D/E", "type": "num", "dp": 2},
    {"key": "reason", "label": "Why", "type": "text", "align": "left"},
]

_RECORD_FIELDS = ["ticker", "sector", "score", "price", "daily_vol", "ret_3m",
                  "ret_6m", "ret_12m", "rel_sector_3m", "pe", "roe", "eps_growth",
                  "debt_equity", "factors", "reason", "signal_notes"]


def _payload(result: dict) -> tuple[list[dict], list[dict]]:
    """Build the per-record JSON rows (with screen membership) and screen metadata."""
    records = result.get("records", [])
    membership: dict[str, set] = {}
    screen_meta: list[dict] = []
    for screen in SCREENS:
        hits = apply_screen(screen, records)
        membership[screen.key] = {r.ticker for r in hits}
        screen_meta.append({
            "key": screen.key, "name": screen.name, "description": screen.description,
            "sort_by": screen.sort_by, "sort_desc": screen.sort_desc, "count": len(hits),
        })

    rows = []
    for r in records:
        row = {f: getattr(r, f) for f in _RECORD_FIELDS}
        row["screens"] = [k for k, tickers in membership.items() if r.ticker in tickers]
        rows.append(row)
    return rows, screen_meta


def _json_for_html(obj: Any) -> str:
    # Escape "<" so a stray "</script>" in data can't close the tag early.
    return json.dumps(obj, default=str).replace("<", "\\u003c")


# The four deployed pages, their path from the site root, and their depth (how
# many levels up to reach the root) — used to build relative cross-links.
_PAGES = [
    ("us_daily", "🇺🇸 US Screener", ""),
    ("us_fund", "🇺🇸 US Fundamentals", "fundamentals/"),
    ("in_daily", "🇮🇳 India Screener", "in/"),
    ("in_fund", "🇮🇳 India Fundamentals", "in/fundamentals/"),
]
_DEPTH = {"us_daily": 0, "us_fund": 1, "in_daily": 1, "in_fund": 2}


def nav_html(current: str) -> str:
    """A cross-page/cross-market nav bar with relative links from ``current``."""
    up = "../" * _DEPTH[current]
    links = []
    for key, label, path in _PAGES:
        href = (up + path) or "./"
        cls = "navlink active" if key == current else "navlink"
        links.append(f'<a class="{cls}" href="{href}">{label}</a>')
    return '<nav class="nav">' + "".join(links) + "</nav>"


def render_screener_body(header_html: str, rows: list[dict],
                         screen_meta: list[dict], columns: list[dict],
                         score_label: str = "Min score", currency: str = "$") -> str:
    """Generic interactive screener body: a header block + tabbed sortable tables.

    Reused by both the daily site and the fundamental screener — only the header,
    records, screens, and columns differ. No <html>/<head>/<body> (Artifact-ready).
    """
    return f"""
<style>{STYLE}</style>
<div class="app">
{header_html}
  <div class="tabs" id="tabs" role="tablist"></div>
  <p class="tabdesc" id="tabdesc"></p>

  <div class="controls">
    <input type="search" id="search" placeholder="Search ticker or sector…" aria-label="Search">
    <select id="sector" aria-label="Filter by sector"><option value="">All sectors</option></select>
    <label>{html.escape(score_label)} <input type="range" id="minscore" min="0" max="100" value="0" step="5">
      <span id="minscoreval">0</span></label>
    <span class="spacer"></span>
    <span class="count" id="count"></span>
    <button class="btn" id="export" type="button">Export CSV</button>
  </div>

  <div class="tablewrap">
    <table><thead id="thead"></thead><tbody id="tbody"></tbody></table>
  </div>
</div>
<script>
const CURRENCY = {_json_for_html(currency)};
const RECORDS = {_json_for_html(rows)};
const SCREENS = {_json_for_html(screen_meta)};
const COLUMNS = {_json_for_html(columns)};
</script>
<script>{SCRIPT}</script>
"""


_FACTOR_INFO = {
    "sector": ("Sector tailwind", "the stock's sector is Leading or Improving on the RRG"),
    "trend": ("Trend", "positive 3M / 6M / 12M returns and price above its 50 & 200-day averages"),
    "rel_strength": ("Relative strength", "beating its own sector over the last 3 months"),
    "volatility": ("Volatility fit", "daily moves lively enough to trade, not chaotic"),
    "trigger": ("Trigger", "a fresh catalyst today — 52-week-high breakout, 2×+ volume, MACD cross, or a big up-day"),
    "fundamental": ("Fundamental", "value + quality + growth from the fundamentals snapshot"),
}


def conviction_methodology_html(currency: str = "$") -> str:
    """Explain the Daily Conviction Score, generated from the live weights/gates."""
    from screener.scoring import DEFAULT_WEIGHTS, Gates
    g = Gates()
    rows = "".join(
        f"<li><b>{_FACTOR_INFO[k][0]}</b> · {round(DEFAULT_WEIGHTS[k] * 100)}% — {_FACTOR_INFO[k][1]}</li>"
        for k in DEFAULT_WEIGHTS if k in _FACTOR_INFO
    )
    return (
        '<details class="method"><summary>ℹ︎ How the Conviction Score works</summary>'
        "<p>Each stock gets a <b>0–100 Daily Conviction Score</b> — a weighted blend of six "
        "factors (higher = stronger confluence), behind hard gates:</p>"
        f"<ul>{rows}</ul>"
        f'<p class="muted">Gates (excluded if failed): price ≥ {currency}{g.min_price:.0f} and '
        f"≥ {currency}{g.min_dollar_vol / 1e6:.0f}M average daily turnover; drop negative or "
        f"&gt;{g.max_pe:.0f} P/E and debt/equity &gt; {g.max_debt_equity:.1f}. "
        "Missing fundamentals leave that factor neutral.</p></details>"
    )


def build_site_body(result: dict, rrg_data_uri: str | None) -> str:
    """Inner content for the daily technical screener site (market-aware)."""
    rows, screen_meta = _payload(result)
    market = result.get("market", "us")
    label = result.get("market_label", "US")
    currency = result.get("currency", "$")
    benchmark = "Nifty" if market == "in" else "SPY"
    best = max((r["score"] for r in rows if isinstance(r["score"], (int, float))), default=0)
    chips = "".join(
        f'<span class="chip">{html.escape(s)}</span>' for s in result.get("leading_sectors", [])
    ) or '<span class="muted">none</span>'
    rrg_block = (
        f'<details class="rrg"><summary>Sector Rotation (RRG) — sectors vs {benchmark}</summary>'
        f'<img src="{rrg_data_uri}" alt="Relative Rotation Graph of sectors vs {benchmark}"></details>'
        if rrg_data_uri else ""
    )
    header = f"""  {nav_html(f"{market}_daily")}
  <h1>📈 {html.escape(label)} Daily Screener</h1>
  <div class="meta">As of <b>{html.escape(str(result.get("as_of", "")))}</b> ·
    universe {html.escape(str(result.get("universe", "")))} ·
    scored {result.get("scored", 0)} of {result.get("scanned", 0)}
    (filtered {result.get("filtered_out", 0)}) ·
    <a href="./fundamentals/">Fundamental screener →</a></div>
  <div class="tiles">
    <div class="tile"><div class="k">{result.get("scored", 0)}</div><div class="l">Passed gate</div></div>
    <div class="tile"><div class="k">{best:.0f}</div><div class="l">Best score</div></div>
    <div class="tile"><div class="k">{len(screen_meta)}</div><div class="l">Screens</div></div>
    <div class="tile"><div class="k">{len(result.get("leading_sectors", []))}</div><div class="l">Tailwind sectors</div></div>
  </div>
  <div class="chips"><b style="color:var(--muted)">SECTOR TAILWINDS&nbsp;&nbsp;</b>{chips}</div>
  {conviction_methodology_html(currency)}
  {rrg_block}"""
    return render_screener_body(header, rows, screen_meta, COLUMNS, currency=currency)


def wrap_page(body: str, title: str = "Daily Stock Screener") -> str:
    """Wrap the site body in a full standalone HTML document (GitHub Pages)."""
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        "<style>body{margin:0;background:#fcfcfb}"
        "@media(prefers-color-scheme:dark){body{background:#141413}}</style>\n"
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n"
    )


def build_site(result: dict, rrg_data_uri: str | None) -> str:
    """Full standalone HTML page for GitHub Pages."""
    return wrap_page(build_site_body(result, rrg_data_uri))
