from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import html

from prettytable import PrettyTable

from screener.fundamentals import get_fundamentals, grade
from screener.web import render_screener_body, wrap_page

logger = logging.getLogger(__name__)

# Dense, ChartMill-style column set. "score" cells render as 0-100 rating badges.
COLUMNS = [
    {"key": "rank", "label": "#", "type": "num", "sortable": False},
    {"key": "ticker", "label": "Ticker", "type": "text", "align": "left"},
    {"key": "letter", "label": "Grade", "type": "text"},
    {"key": "score", "label": "Overall", "type": "score"},
    {"key": "value", "label": "Value", "type": "score"},
    {"key": "quality", "label": "Quality", "type": "score"},
    {"key": "growth", "label": "Growth", "type": "score"},
    {"key": "health", "label": "Health", "type": "score"},
    {"key": "dividend_yield", "label": "Yield", "type": "pct"},
    {"key": "pe", "label": "P/E", "type": "num", "dp": 1},
    {"key": "forward_pe", "label": "Fwd P/E", "type": "num", "dp": 1},
    {"key": "peg", "label": "PEG", "type": "num", "dp": 2},
    {"key": "ps", "label": "P/S", "type": "num", "dp": 1},
    {"key": "roe", "label": "ROE", "type": "pct"},
    {"key": "roa", "label": "ROA", "type": "pct"},
    {"key": "net_margin", "label": "Net M", "type": "pct"},
    {"key": "eps_growth", "label": "EPS gr", "type": "pct"},
    {"key": "sales_growth", "label": "Sales gr", "type": "pct"},
    {"key": "debt_equity", "label": "D/E", "type": "num", "dp": 2},
    {"key": "current_ratio", "label": "Curr R", "type": "num", "dp": 2},
    {"key": "sector", "label": "Sector", "type": "text", "align": "left"},
    {"key": "industry", "label": "Industry", "type": "text", "align": "left"},
]


def _n(v) -> float:
    return v if isinstance(v, (int, float)) else float("-inf")


@dataclass(frozen=True)
class FScreen:
    key: str
    name: str
    description: str
    predicate: Callable[[dict], bool]
    sort_by: str = "score"


SCREENS: list[FScreen] = [
    FScreen("leaders", "Fundamental Leaders",
            "Best overall fundamental grade.", lambda r: r["score"] is not None),
    FScreen("deep_value", "Deep Value",
            "Cheap on earnings, sales, book and cash flow.",
            lambda r: _n(r["value"]) >= 70, "value"),
    FScreen("high_quality", "High Quality",
            "Strong returns on capital and fat margins.",
            lambda r: _n(r["quality"]) >= 70, "quality"),
    FScreen("high_growth", "High Growth",
            "Fast earnings and sales growth.",
            lambda r: _n(r["growth"]) >= 70, "growth"),
    FScreen("fortress", "Fortress Balance Sheet",
            "Low debt with healthy liquidity.",
            lambda r: _n(r["health"]) >= 70, "health"),
    FScreen("garp", "Growth at a Reasonable Price",
            "Solid growth without paying up for it.",
            lambda r: _n(r["growth"]) >= 60 and _n(r["value"]) >= 55),
    FScreen("dividend", "Dividend Payers",
            "Meaningful dividend yield.",
            lambda r: _n(r["dividend_yield"]) >= 2, "dividend_yield"),
]

_ROW_METRICS = ["pe", "forward_pe", "peg", "ps", "roe", "roa", "net_margin",
                "eps_growth", "sales_growth", "debt_equity", "current_ratio",
                "dividend_yield", "sector", "industry", "market_cap"]


def build_rows(funds: dict) -> tuple[list[dict], list[dict]]:
    """Grade every stock, keep the graded ones, and tag screen membership."""
    rows: list[dict] = []
    for ticker, f in funds.items():
        g = grade(f)
        if g.overall is None:
            continue
        row = {"ticker": ticker, "letter": g.letter, "score": g.overall,
               "value": g.value, "quality": g.quality, "growth": g.growth,
               "health": g.health, "dividend": g.dividend}
        row.update({m: getattr(f, m) for m in _ROW_METRICS})
        rows.append(row)

    membership: dict[str, set] = {}
    screen_meta: list[dict] = []
    for s in SCREENS:
        hits = sorted((r for r in rows if s.predicate(r)),
                      key=lambda r: _n(r[s.sort_by]), reverse=True)
        membership[s.key] = {r["ticker"] for r in hits}
        screen_meta.append({"key": s.key, "name": s.name, "description": s.description,
                            "sort_by": s.sort_by, "sort_desc": True, "count": len(hits)})
    for r in rows:
        r["screens"] = [k for k, tickers in membership.items() if r["ticker"] in tickers]
    return rows, screen_meta


def build_body(funds: dict, as_of: str = "", universe: str = "sp500") -> str:
    rows, screen_meta = build_rows(funds)
    grades = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for r in rows:
        grades[r["letter"]] = grades.get(r["letter"], 0) + 1
    best = max((r["score"] for r in rows), default=0)
    header = f"""  <h1>🧮 Fundamental Screener</h1>
  <div class="meta">As of <b>{html.escape(str(as_of))}</b> · universe {html.escape(universe)} ·
    graded {len(rows)} stocks · <a href="../">← Daily screener</a></div>
  <div class="tiles">
    <div class="tile"><div class="k">{len(rows)}</div><div class="l">Graded</div></div>
    <div class="tile"><div class="k">{grades['A']}</div><div class="l">A-grade</div></div>
    <div class="tile"><div class="k">{best:.0f}</div><div class="l">Best overall</div></div>
    <div class="tile"><div class="k">{len(screen_meta)}</div><div class="l">Screens</div></div>
  </div>"""
    return render_screener_body(header, rows, screen_meta, COLUMNS, score_label="Min grade")


def build_page(funds: dict, as_of: str = "", universe: str = "sp500") -> str:
    return wrap_page(build_body(funds, as_of, universe), title="Fundamental Screener")


def format_table(rows: list[dict], top: int = 25) -> str:
    table = PrettyTable()
    table.field_names = ["#", "Ticker", "Grade", "Overall", "Val", "Qual", "Grw",
                         "Hlth", "P/E", "ROE", "EPS gr", "D/E", "Sector"]
    table.align = "r"
    for c in ("Ticker", "Grade", "Sector"):
        table.align[c] = "l"
    ranked = sorted(rows, key=lambda r: _n(r["score"]), reverse=True)[:top]
    for i, r in enumerate(ranked, 1):
        table.add_row([i, r["ticker"], r["letter"], _f(r["score"]), _f(r["value"]),
                       _f(r["quality"]), _f(r["growth"]), _f(r["health"]),
                       _f(r["pe"]), _p(r["roe"]), _p(r["eps_growth"]), _f(r["debt_equity"]),
                       (r["sector"] or "?")[:18]])
    table.title = f"Fundamental Leaders — top {len(ranked)} of {len(rows)} graded"
    return table.get_string()


def _f(v):
    return f"{v:.0f}" if isinstance(v, (int, float)) else "-"


def _p(v):
    return f"{v:.0f}%" if isinstance(v, (int, float)) else "-"


def main() -> None:
    parser = argparse.ArgumentParser(description="Fundamentals-only stock screener")
    parser.add_argument("--market", default="us")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--html", type=str, default=None, help="Write the interactive page here")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    funds = get_fundamentals(args.market)
    if not funds:
        print("No fundamentals snapshot found. Run: python -m screener.fundamentals --market "
              f"{args.market}")
        return
    as_of = next(iter(funds.values())).as_of
    rows, _ = build_rows(funds)
    print("\n" + format_table(rows, top=args.top))

    if args.html:
        Path(args.html).parent.mkdir(parents=True, exist_ok=True)
        Path(args.html).write_text(build_page(funds, as_of, args.market), encoding="utf-8")
        print(f"\nSaved fundamental screener to {args.html}")


if __name__ == "__main__":
    main()
