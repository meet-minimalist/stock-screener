from __future__ import annotations

import base64
import html
from typing import Any

from screener.reports.rrg_chart import build_rrg_chart
from screener.screeners.sector_rotation import compute_rrg_tails

# Score tiers -> badge colour (reserved status palette; validated for CVD).
_TIER_COLORS = [
    (80, "#0ca30c"),   # strong
    (65, "#2a78d6"),   # solid
    (50, "#fab219"),   # watch
    (0,  "#898781"),   # weak
]

# Per-factor bar colours (categorical, fixed order).
_FACTOR_COLORS = {
    "sector": "#2a78d6",
    "trend": "#1baf7a",
    "rel_strength": "#eda100",
    "volatility": "#4a3aa7",
    "trigger": "#eb6834",
}
_FACTOR_LABEL = {
    "sector": "Sector", "trend": "Trend", "rel_strength": "Rel str",
    "volatility": "Vol fit", "trigger": "Trigger",
}


def _tier_color(score: float) -> str:
    for threshold, color in _TIER_COLORS:
        if score >= threshold:
            return color
    return _TIER_COLORS[-1][1]


def render_rrg_data_uri(start_date: str, end_date: str, interval: str = "1d",
                        rrg_window: int = 63, tail_weeks: int = 12,
                        cache_dir: str = "data/yfinance_cache") -> str | None:
    """Render the RRG chart to a base64 PNG data URI (self-contained, no CDN).

    Returns None if the chart can't be produced (e.g. kaleido missing or no
    data) so the dashboard still renders without it.
    """
    try:
        tails = compute_rrg_tails(start_date, end_date, interval=interval,
                                  rrg_window=rrg_window, tail_weeks=tail_weeks,
                                  cache_dir=cache_dir)
        if not tails:
            return None
        fig = build_rrg_chart(tails)
        fig.update_layout(paper_bgcolor="white", plot_bgcolor="white")
        png = fig.to_image(format="png", width=1000, height=760, scale=2)
    except Exception:
        return None
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _factor_bars(factors: dict[str, float]) -> str:
    cells = []
    for key, color in _FACTOR_COLORS.items():
        val = float(factors.get(key, 0.0))
        pct = max(0, min(100, round(val * 100)))
        cells.append(
            f'<span class="fbar" title="{_FACTOR_LABEL[key]} {pct}%">'
            f'<span class="fbar-fill" style="height:{pct}%;background:{color}"></span>'
            f'</span>'
        )
    return f'<span class="fbars">{"".join(cells)}</span>'


def _ret(v) -> str:
    if not isinstance(v, (int, float)):
        return '<span class="muted">n/a</span>'
    cls = "pos" if v > 0 else "neg" if v < 0 else "muted"
    return f'<span class="{cls}">{v:+.0f}%</span>'


def build_dashboard_body(result: dict[str, Any], rrg_data_uri: str | None) -> str:
    """Inner page content (a <style> block + markup) — no <html>/<head>/<body>.

    Usable directly as a Claude Artifact and wrappable into a full page for
    GitHub Pages via wrap_page().
    """
    top = result["top"]
    top_score = top[0]["score"] if top else 0
    chips = "".join(
        f'<span class="chip">{html.escape(s)}</span>' for s in result["leading_sectors"]
    ) or '<span class="muted">none</span>'

    rows = []
    for i, r in enumerate(top, 1):
        rows.append(
            "<tr>"
            f'<td class="rank">{i}</td>'
            f'<td class="tk">{html.escape(r["ticker"])}</td>'
            f'<td><span class="score" style="background:{_tier_color(r["score"])}">{r["score"]:.0f}</span></td>'
            f'<td>{_factor_bars(r["factors"])}</td>'
            f'<td class="num">${r["price"]:,.2f}</td>'
            f'<td>{html.escape((r["sector"] or "?"))}</td>'
            f'<td class="num">{r["daily_vol"]:.1f}%</td>'
            f'<td class="num">{_ret(r["ret_3m"])}</td>'
            f'<td class="num">{_ret(r["ret_12m"])}</td>'
            f'<td class="why">{html.escape(r["reason"])}</td>'
            "</tr>"
        )

    rrg_block = (
        f'<img class="rrg" src="{rrg_data_uri}" alt="Relative Rotation Graph of sectors vs SPY">'
        if rrg_data_uri else
        '<p class="muted">RRG chart unavailable for this run.</p>'
    )

    return f"""
<style>
  .dash {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    max-width: 1180px; margin: 0 auto; padding: 24px 20px 64px;
    color: var(--ink); }}
  .dash {{ --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --surface:#fcfcfb;
    --card:#ffffff; --line:#e1e0d9; --pos:#0a7a0a; --neg:#c0392b; }}
  @media (prefers-color-scheme: dark) {{
    .dash {{ --ink:#f4f4f2; --ink2:#c3c2b7; --muted:#8f8e88; --surface:#141413;
      --card:#1c1c1a; --line:#2c2c2a; --pos:#28b528; --neg:#e26d5c; }}
  }}
  :root[data-theme="dark"] .dash {{ --ink:#f4f4f2; --ink2:#c3c2b7; --muted:#8f8e88;
    --surface:#141413; --card:#1c1c1a; --line:#2c2c2a; --pos:#28b528; --neg:#e26d5c; }}
  :root[data-theme="light"] .dash {{ --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
    --surface:#fcfcfb; --card:#ffffff; --line:#e1e0d9; --pos:#0a7a0a; --neg:#c0392b; }}
  .dash h1 {{ font-size: 1.5rem; margin: 0 0 2px; }}
  .dash .meta {{ color: var(--ink2); font-size: .85rem; margin-bottom: 20px; }}
  .tiles {{ display:flex; flex-wrap:wrap; gap:12px; margin-bottom:20px; }}
  .tile {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
    padding:12px 16px; min-width:120px; }}
  .tile .k {{ font-size:1.5rem; font-weight:650; }}
  .tile .l {{ font-size:.72rem; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
  .chips {{ margin:0 0 20px; }}
  .chip {{ display:inline-block; background:rgba(12,163,12,.14); color:var(--ink);
    border:1px solid rgba(12,163,12,.35); border-radius:999px; padding:2px 10px;
    font-size:.8rem; margin:0 6px 6px 0; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px;
    padding:8px; margin-bottom:24px; overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; font-size:.86rem; }}
  th, td {{ padding:9px 10px; text-align:left; border-bottom:1px solid var(--line);
    white-space:nowrap; }}
  th {{ color:var(--muted); font-weight:600; font-size:.72rem; text-transform:uppercase;
    letter-spacing:.03em; }}
  td.num, th.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .rank {{ color:var(--muted); }}
  .tk {{ font-weight:650; }}
  .score {{ display:inline-block; min-width:34px; text-align:center; color:#fff;
    border-radius:7px; padding:2px 7px; font-weight:650; font-variant-numeric:tabular-nums; }}
  .why {{ color:var(--ink2); white-space:normal; min-width:220px; }}
  .pos {{ color:var(--pos); }} .neg {{ color:var(--neg); }} .muted {{ color:var(--muted); }}
  .fbars {{ display:inline-flex; align-items:flex-end; gap:2px; height:20px; }}
  .fbar {{ position:relative; width:5px; height:100%; background:var(--line);
    border-radius:2px; overflow:hidden; }}
  .fbar-fill {{ position:absolute; bottom:0; left:0; width:100%; border-radius:2px; }}
  img.rrg {{ display:block; width:100%; height:auto; border-radius:10px; }}
  h2 {{ font-size:1.05rem; margin:0 0 10px; }}
</style>
<div class="dash">
  <h1>📈 Daily Conviction Picks</h1>
  <div class="meta">As of <b>{html.escape(str(result["as_of"]))}</b> ·
    universe {html.escape(str(result["universe"]))} ·
    scored {result["scored"]} of {result["scanned"]} (filtered {result["filtered_out"]})</div>

  <div class="tiles">
    <div class="tile"><div class="k">{len(top)}</div><div class="l">Top picks</div></div>
    <div class="tile"><div class="k">{top_score:.0f}</div><div class="l">Best score</div></div>
    <div class="tile"><div class="k">{result["scored"]}</div><div class="l">Passed gate</div></div>
    <div class="tile"><div class="k">{len(result["leading_sectors"])}</div><div class="l">Tailwind sectors</div></div>
  </div>

  <div class="chips"><b style="font-size:.8rem;color:var(--muted)">SECTOR TAILWINDS &nbsp;</b>{chips}</div>

  <div class="card">
    <table>
      <thead><tr>
        <th>#</th><th>Ticker</th><th>Score</th><th>Factors</th>
        <th class="num">Price</th><th>Sector</th><th class="num">Vol</th>
        <th class="num">3M</th><th class="num">12M</th><th>Why</th>
      </tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </div>

  <h2>Sector Rotation (RRG)</h2>
  <div class="card">{rrg_block}</div>
</div>
"""


def wrap_page(body: str, title: str = "Daily Conviction Picks") -> str:
    """Wrap the dashboard body in a full standalone HTML document (GitHub Pages)."""
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        "<style>body{margin:0;background:#fcfcfb}"
        "@media(prefers-color-scheme:dark){body{background:#141413}}</style>\n"
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n"
    )
