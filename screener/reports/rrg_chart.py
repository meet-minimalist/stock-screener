from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from screener.screeners.sector_rotation import classify_quadrant

# Quadrant marker colours: the reserved status palette (never series colours),
# validated for CVD separation. Improving uses the info-blue categorical slot.
QUADRANT_COLOR = {
    "Leading": "#0ca30c",    # good
    "Weakening": "#fab219",  # warning
    "Lagging": "#d03b3b",    # critical
    "Improving": "#2a78d6",  # info
    "n/a": "#898781",
}

# Faint translucent quadrant backgrounds that read on both light and dark.
_QUADRANT_BG = {
    "Leading": "rgba(12,163,12,0.10)",
    "Weakening": "rgba(250,178,25,0.10)",
    "Lagging": "rgba(208,59,59,0.10)",
    "Improving": "rgba(42,120,214,0.10)",
}

_MUTED = "#898781"


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def build_rrg_chart(tails: dict[str, pd.DataFrame], benchmark_label: str = "SPY") -> go.Figure:
    """Relative Rotation Graph: RS-Ratio (x) vs RS-Momentum (y), 100 = neutral.

    Each sector is drawn as a tail (its weekly path) ending in a labelled head
    (its current position), coloured by the head's quadrant. Four faint quadrant
    backgrounds and crosshairs at 100 give the read at a glance.
    """
    fig = go.Figure()

    xs: list[float] = []
    ys: list[float] = []
    for t in tails.values():
        xs.extend(t["rs_ratio"].tolist())
        ys.extend(t["rs_momentum"].tolist())
    if xs and ys:
        dev = max(abs(min(xs) - 100), abs(max(xs) - 100),
                  abs(min(ys) - 100), abs(max(ys) - 100))
        dev = max(dev * 1.15, 1.5)
    else:
        dev = 5.0
    lo, hi = 100 - dev, 100 + dev

    # Quadrant background rectangles (drawn beneath the data). Standard RRG layout:
    # Improving is top-left (weak but momentum rising), Weakening is bottom-right
    # (strong but momentum fading).
    for q, (x0, y0, x1, y1) in {
        "Leading": (100, 100, hi, hi),
        "Improving": (lo, 100, 100, hi),
        "Lagging": (lo, lo, 100, 100),
        "Weakening": (100, lo, hi, 100),
    }.items():
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      fillcolor=_QUADRANT_BG[q], line_width=0, layer="below")

    # Crosshairs at the neutral line.
    fig.add_hline(y=100, line=dict(color=_MUTED, width=1, dash="dash"))
    fig.add_vline(x=100, line=dict(color=_MUTED, width=1, dash="dash"))

    # Corner labels naming each quadrant.
    for txt, x, y, xa, ya in [
        ("Leading", hi, hi, "right", "top"),
        ("Improving", lo, hi, "left", "top"),
        ("Lagging", lo, lo, "left", "bottom"),
        ("Weakening", hi, lo, "right", "bottom"),
    ]:
        fig.add_annotation(x=x, y=y, text=txt, showarrow=False,
                           xanchor=xa, yanchor=ya, opacity=0.75,
                           font=dict(size=13, color=_MUTED))

    for sector, t in tails.items():
        etf = str(t["etf"].iloc[-1])
        head_r = float(t["rs_ratio"].iloc[-1])
        head_m = float(t["rs_momentum"].iloc[-1])
        quad = classify_quadrant(head_r, head_m)
        color = QUADRANT_COLOR.get(quad, _MUTED)
        dates = [d.date().isoformat() if hasattr(d, "date") else str(d) for d in t.index]

        # Tail: weekly path leading up to now, drawn as a "comet" — faint/small at
        # the oldest point, brighter/larger toward the head — so direction reads.
        n = len(t)
        if n > 1:
            sizes = [3 + 5 * (i / (n - 1)) for i in range(n)]
            opac = [0.2 + 0.6 * (i / (n - 1)) for i in range(n)]
        else:
            sizes, opac = [8], [0.8]
        fig.add_trace(go.Scatter(
            x=t["rs_ratio"], y=t["rs_momentum"], mode="lines+markers",
            line=dict(color=_rgba(color, 0.35), width=1.5),
            marker=dict(size=sizes, color=color, opacity=opac),
            name=sector, legendgroup=sector, showlegend=False,
            customdata=dates,
            hovertemplate=(f"{sector} ({etf})<br>%{{customdata}}"
                           "<br>RS-Ratio %{x:.1f}<br>RS-Mom %{y:.1f}<extra></extra>"),
        ))

        # Head: current position, larger, labelled with the ETF ticker.
        fig.add_trace(go.Scatter(
            x=[head_r], y=[head_m], mode="markers+text",
            marker=dict(size=13, color=color, line=dict(color="#fcfcfb", width=1.5)),
            text=[etf], textposition="top center", textfont=dict(size=11),
            name=sector, legendgroup=sector, showlegend=False,
            hovertemplate=(f"<b>{sector} ({etf})</b><br>{quad}"
                           f"<br>RS-Ratio {head_r:.1f}<br>RS-Mom {head_m:.1f}<extra></extra>"),
        ))

    fig.update_layout(
        title=f"Relative Rotation Graph — sectors vs {benchmark_label} (head = now, tail = past weeks)",
        xaxis_title="RS-Ratio  (relative strength →)",
        yaxis_title="RS-Momentum  (strengthening ↑)",
        xaxis=dict(range=[lo, hi], zeroline=False),
        yaxis=dict(range=[lo, hi], zeroline=False),
        height=650, margin=dict(l=60, r=30, t=60, b=60),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig
