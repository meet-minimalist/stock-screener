from __future__ import annotations

import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
import streamlit as st

from screener.data.universe import get_ticker_list
from screener.reports.chart_markers import build_stock_chart
from screener.screeners.engine import ScreeningEngine
from screener.screeners.strategies import BigGain, BullishMACD, CandlePattern, GoldenCross, HighVolume, Near52WeekHigh, OversoldBounce
from screener.screeners.strategies import ALL_PATTERNS, CUSTOM_CDL_LABELS, DEFAULT_CDL_PATTERNS

logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")

STRATEGY_MAP: dict[str, type] = {
    "Oversold Bounce (RSI < 30)": OversoldBounce,
    "Bullish MACD": BullishMACD,
    "Golden Cross (SMA20 > SMA50)": GoldenCross,
    "Near 52-Week High": Near52WeekHigh,
    "Big Single-Day Gain (>=5%)": BigGain,
    "High Volume vs SMA (2x avg)": HighVolume,
    "Candlestick Patterns": CandlePattern,
}

UNIVERSE_OPTIONS = {
    "S&P 500": "sp500",
    "Custom CSV": "custom_csv",
}

KEYS = [
    "scan_done", "results", "data_map", "filtered_results",
    "strategy_name", "strategy_cls", "sma_periods", "rsi_periods",
    "macd_config", "needs_macd", "cdl_patterns",
]

st.set_page_config(page_title="Stock Screener", layout="wide")

for k in KEYS:
    if k not in st.session_state:
        st.session_state[k] = None

st.title("Stock Technical Screener")

with st.sidebar:
    st.header("Configuration")

    universe_name = st.selectbox("Stock Universe", list(UNIVERSE_OPTIONS), index=0)
    universe_src = UNIVERSE_OPTIONS[universe_name]
    if universe_src == "custom_csv":
        uploaded = st.file_uploader("Upload CSV with tickers", type=["csv"])
        if uploaded:
            csv_path = f"data/uploads/{uploaded.name}"
            Path("data/uploads").mkdir(parents=True, exist_ok=True)
            with open(csv_path, "wb") as f:
                f.write(uploaded.getbuffer())
            universe_src = csv_path

    strategy_name = st.selectbox("Strategy", list(STRATEGY_MAP), index=0)
    strategy_cls = STRATEGY_MAP[strategy_name]

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.text_input("Start Date", "2025-06-22")
    with col2:
        end_date = st.text_input("End Date", "2026-06-22")

    interval = st.selectbox("Interval", ["1d", "1h", "15m", "5m"], index=0)

    cdl_patterns = DEFAULT_CDL_PATTERNS
    if strategy_cls == CandlePattern:
        cdl_options = sorted(ALL_PATTERNS, key=lambda p: CUSTOM_CDL_LABELS.get(p, p))
        cdl_labels = {p: CUSTOM_CDL_LABELS.get(p, p) for p in cdl_options}
        cdl_selected = st.multiselect(
            "Candle Patterns",
            options=cdl_options,
            default=DEFAULT_CDL_PATTERNS,
            format_func=lambda p: cdl_labels[p],
            help="Select candlestick patterns to scan for",
        )
        if cdl_selected:
            cdl_patterns = cdl_selected

    max_tickers = st.number_input("Max tickers to scan", min_value=1, max_value=10000, value=100)

    run_clicked = st.button("Run Scan", type="primary", use_container_width=True)

if run_clicked:
    with st.spinner("Loading ticker universe..."):
        try:
            all_tickers = get_ticker_list(universe_src)
        except Exception as e:
            st.error(f"Failed to load ticker list: {e}")
            st.stop()

    tickers = all_tickers[:max_tickers]
    st.info(f"Scanning {len(tickers)} tickers from {universe_name}")

    strategy = strategy_cls(patterns=cdl_patterns) if strategy_cls == CandlePattern else strategy_cls()
    engine = ScreeningEngine()

    sma_periods = [20, 50]
    rsi_periods = [14]
    macd_config = {"fast": 12, "slow": 26, "signal": 9}
    needs_macd = "MACD" in strategy_name

    progress_bar = st.progress(0, text="Scanning...")
    status_text = st.empty()

    results: list[dict] = []
    data_map: dict[str, pd.DataFrame] = {}

    for i, ticker in enumerate(tickers):
        status_text.text(f"Processing {ticker}... ({i+1}/{len(tickers)})")
        progress_bar.progress((i + 1) / len(tickers))

        df = engine.fetcher.get_data(ticker, start_date, end_date, interval=interval)
        if df.empty:
            continue

        df = engine.calculator.compute(
            df,
            sma_periods=sma_periods,
            rsi_periods=rsi_periods,
            macd_config=macd_config if needs_macd else None,
        )

        result = strategy.filter(ticker, df)
        results.append(result)
        data_map[ticker] = df

    progress_bar.empty()
    status_text.empty()

    filtered_results = [r for r in results if r.get("signal") in ("BUY", "SELL")]

    st.session_state.scan_done = True
    st.session_state.results = results
    st.session_state.data_map = data_map
    st.session_state.filtered_results = filtered_results
    st.session_state.strategy_name = strategy_name
    st.session_state.strategy_cls = strategy_cls
    st.session_state.sma_periods = sma_periods
    st.session_state.rsi_periods = rsi_periods
    st.session_state.macd_config = macd_config
    st.session_state.needs_macd = needs_macd
    st.session_state.cdl_patterns = cdl_patterns

    st.rerun()

if st.session_state.scan_done:
    results = st.session_state.results
    data_map = st.session_state.data_map
    filtered_results = st.session_state.filtered_results
    strategy_name = st.session_state.strategy_name
    strategy_cls = st.session_state.strategy_cls
    sma_periods = st.session_state.sma_periods
    rsi_periods = st.session_state.rsi_periods
    needs_macd = st.session_state.needs_macd
    cdl_patterns = st.session_state.cdl_patterns

    st.success(f"Scan complete — processed {len(results)} tickers")

    if not filtered_results:
        st.warning("No stocks matched the screening criteria.")
    else:
        st.subheader(f"Results: {len(filtered_results)} / {len(results)} signals")

        cols = ["ticker", "last_price", "signal", "signal_date", "reason"]
        extra_cols = [
            k for k in filtered_results[0]
            if k not in cols and k not in ("marker_dates",)
        ]
        cols[3:3] = extra_cols

        table_data = []
        for r in filtered_results:
            row = {k: r.get(k, "") for k in cols}
            table_data.append(row)

        df_table = pd.DataFrame(table_data)
        df_table["last_price"] = df_table["last_price"].apply(
            lambda x: f"${x:.2f}" if isinstance(x, (int, float)) else x
        )

        st.dataframe(df_table, use_container_width=True, hide_index=True)

        st.subheader("Chart View")
        selected_ticker = st.selectbox(
            "Select a ticker to view chart",
            [r["ticker"] for r in filtered_results],
            key="ticker_selector",
        )

        if selected_ticker and selected_ticker in data_map:
            df_chart = data_map[selected_ticker]
            strategy = strategy_cls(patterns=cdl_patterns) if strategy_cls == CandlePattern else strategy_cls()
            strategy._df = df_chart
            if strategy_cls == CandlePattern:
                strategy._pattern_results = None
            markers = strategy.get_signal_markers()

            with st.spinner("Generating chart..."):
                fig = build_stock_chart(
                    ticker=selected_ticker,
                    df=df_chart,
                    markers=markers,
                    sma_periods=sma_periods,
                    rsi_period=rsi_periods[0],
                    show_macd=needs_macd,
                )
                st.plotly_chart(fig, use_container_width=True)

            with st.expander("Raw Data"):
                st.dataframe(df_chart.tail(20), use_container_width=True)

    if st.button("New Scan", type="secondary"):
        for k in KEYS:
            st.session_state[k] = None
        st.rerun()
else:
    st.info("Configure the scan parameters in the sidebar and click **Run Scan**.")
