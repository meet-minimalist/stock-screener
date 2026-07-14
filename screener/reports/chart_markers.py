from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def build_stock_chart(
    ticker: str,
    df: pd.DataFrame,
    markers: list[dict] | None = None,
    sma_periods: list[int] | None = None,
    rsi_period: int | None = 14,
    show_macd: bool = False,
) -> go.Figure:
    is_datetime_idx = isinstance(df.index, pd.DatetimeIndex)
    idx = df.index if is_datetime_idx else pd.to_datetime(df.index)

    if show_macd:
        n_rows = 4
        row_heights = [0.4, 0.15, 0.2, 0.2]
        rsi_row = 3
        macd_row = 4
    else:
        n_rows = 3
        row_heights = [0.5, 0.2, 0.3]
        rsi_row = 3

    vol_row = 2

    fig = make_subplots(
        rows=n_rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=row_heights,
    )

    fig.add_trace(
        go.Candlestick(
            x=idx,
            open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"],
            name="Price",
        ),
        row=1, col=1,
    )

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    if sma_periods:
        for i, p in enumerate(sma_periods):
            col = f"SMA_{p}"
            if col in df.columns:
                fig.add_trace(
                    go.Scatter(x=idx, y=df[col], mode="lines",
                               name=col, line=dict(color=colors[i % len(colors)], width=1)),
                    row=1, col=1,
                )

    if "Volume" in df.columns:
        vol_colors = ["#26a69a" if c >= o else "#ef5350"
                      for c, o in zip(df["Close"], df["Open"])]
        fig.add_trace(
            go.Bar(x=idx, y=df["Volume"], name="Volume",
                   marker_color=vol_colors, opacity=0.7),
            row=vol_row, col=1,
        )
        fig.update_yaxes(title_text="Volume", row=vol_row, col=1)

    if rsi_period is not None:
        rsi_col = f"RSI_{rsi_period}"
        if rsi_col in df.columns:
            fig.add_trace(
                go.Scatter(x=idx, y=df[rsi_col], mode="lines",
                           name=rsi_col, line=dict(color="#7f7f7f", width=1)),
                row=rsi_row, col=1,
            )
            fig.add_hline(y=30, line=dict(color="green", dash="dash", width=1), row=rsi_row, col=1)
            fig.add_hline(y=70, line=dict(color="red", dash="dash", width=1), row=rsi_row, col=1)
            fig.update_yaxes(title_text="RSI", row=rsi_row, col=1)

    if show_macd:
        macd_cols = [c for c in df.columns if c.startswith("MACD_") or c == "MACD"]
        signal_cols = [c for c in df.columns if "MACDs" in c]
        hist_cols = [c for c in df.columns if "MACDh" in c]
        if macd_cols:
            fig.add_trace(
                go.Scatter(x=idx, y=df[macd_cols[0]], mode="lines",
                           name="MACD", line=dict(color="blue", width=1.5)),
                row=macd_row, col=1,
            )
        if signal_cols:
            fig.add_trace(
                go.Scatter(x=idx, y=df[signal_cols[0]], mode="lines",
                           name="Signal", line=dict(color="orange", width=1.5)),
                row=macd_row, col=1,
            )
        if hist_cols:
            colors_hist = ["green" if v >= 0 else "red" for v in df[hist_cols[0]].fillna(0)]
            fig.add_trace(
                go.Bar(x=idx, y=df[hist_cols[0]], name="Histogram",
                       marker_color=colors_hist, opacity=0.5),
                row=macd_row, col=1,
            )
        fig.update_yaxes(title_text="MACD", row=macd_row, col=1)

    high_52w = _compute_52w_high(df)
    low_52w = _compute_52w_low(df)
    if high_52w is not None:
        fig.add_hline(y=high_52w, line=dict(color="purple", dash="dash", width=1.5),
                      annotation_text=f"52w High {high_52w:.2f}", row=1, col=1)
    if low_52w is not None:
        fig.add_hline(y=low_52w, line=dict(color="orange", dash="dash", width=1.5),
                      annotation_text=f"52w Low {low_52w:.2f}", row=1, col=1)

    if markers:
        marker_shapes = {
            "golden_cross": {"color": "green", "symbol": "triangle-up", "size": 12, "label": "Golden Cross"},
            "death_cross": {"color": "red", "symbol": "triangle-down", "size": 12, "label": "Death Cross"},
            "macd_buy": {"color": "green", "symbol": "triangle-up", "size": 10, "label": "MACD Buy"},
            "macd_sell": {"color": "red", "symbol": "triangle-down", "size": 10, "label": "MACD Sell"},
            "oversold": {"color": "green", "symbol": "triangle-up", "size": 10, "label": "Oversold"},
            "exit_oversold": {"color": "orange", "symbol": "circle", "size": 8, "label": "Exit Oversold"},
            "52w_high": {"color": "purple", "symbol": "triangle-down", "size": 10, "label": "52w High"},
            "52w_low": {"color": "orange", "symbol": "triangle-up", "size": 10, "label": "52w Low"},
            "near_52w_high": {"color": "purple", "symbol": "diamond", "size": 8, "label": "Near 52w High"},
            "big_gain": {"color": "green", "symbol": "triangle-up", "size": 12, "label": "Big Gain"},
            "high_volume": {"color": "blue", "symbol": "triangle-up", "size": 10, "label": "High Volume"},
            "cdl_pattern": {"color": "#9c27b0", "symbol": "star", "size": 10, "label": "Candle Pattern"},
        }

        for m in markers:
            cfg = marker_shapes.get(m["type"], {"color": "blue", "symbol": "star", "size": 8, "label": m["type"]})
            if m["type"] == "cdl_pattern":
                subtype = m.get("subtype", "bullish")
                cfg = {**cfg, "color": "#4caf50" if subtype == "bullish" else "#f44336"}
            dt = m["date"]
            price = _price_at(df, dt)
            if price is not None:
                fig.add_annotation(
                    x=dt, y=price,
                    text=m.get("text", cfg["label"]),
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=1.5,
                    arrowcolor=cfg["color"],
                    ax=0, ay=-40 if cfg["symbol"] in ("triangle-up", "diamond") else 40,
                    font=dict(size=9, color=cfg["color"]),
                    bgcolor="rgba(255,255,255,0.8)",
                    bordercolor=cfg["color"],
                    borderwidth=1,
                    borderpad=2,
                )
                fig.add_vline(x=dt, line=dict(color=cfg["color"], dash="dot", width=1.5), opacity=0.5)

    date_col = _get_date_col(df)
    if date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col])
        idx = df[date_col]

    fig.update_xaxes(
        rangebreaks=[dict(bounds=["sat", "mon"])],
        row=1, col=1,
    )

    fig.update_layout(
        title=f"{ticker} — Price & Indicators",
        xaxis_title="Date",
        yaxis_title="Price",
        height=800 if show_macd else 700,
        hovermode="x unified",
        showlegend=True,
        template="plotly_white",
        xaxis_rangeslider_visible=False,
    )

    return fig


def _price_at(df: pd.DataFrame, dt) -> float | None:
    if isinstance(df.index, pd.DatetimeIndex):
        if dt in df.index:
            return float(df.loc[dt, "Close"])
        idx = df.index.sort_values()
        nearest = idx[idx <= dt]
        if not nearest.empty:
            return float(df.loc[nearest[-1], "Close"])
        return float(df.iloc[0]["Close"])
    date_col = _get_date_col(df)
    if date_col in df.columns:
        match = df[df[date_col] == dt]
        if not match.empty:
            return float(match.iloc[0]["Close"])
    return None


def _get_date_col(df: pd.DataFrame) -> str:
    if isinstance(df.index, pd.DatetimeIndex):
        return "Datetime"
    for c in ["Datetime", "Date", "date", "timestamp"]:
        if c in df.columns:
            return c
    return df.columns[0]


def _compute_52w_high(df: pd.DataFrame) -> float | None:
    if "Close" not in df.columns:
        return None
    window = min(252, len(df))
    if window < 20:
        return None
    return float(df["Close"].rolling(window=window, min_periods=1).max().iloc[-1])


def _compute_52w_low(df: pd.DataFrame) -> float | None:
    if "Close" not in df.columns:
        return None
    window = min(252, len(df))
    if window < 20:
        return None
    return float(df["Close"].rolling(window=window, min_periods=1).min().iloc[-1])
