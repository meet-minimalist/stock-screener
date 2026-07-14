from screener.data.fetcher import DataFetcher
from screener.screeners.strategies import BigGain
import pandas as pd

f = DataFetcher()
tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "JNJ"]

# Check max daily gain per ticker
for t in tickers:
    df = f.get_data(t, "2025-06-22", "2026-06-22", "1d")
    if df.empty:
        print(f"{t:6s}: no data")
        continue
    pct = df["Close"].pct_change() * 100
    max_gain = pct.max()
    latest = pct.dropna().iloc[-1]
    print(f"{t:6s}: max_gain={max_gain:+.1f}%  latest={latest:+.1f}%")

# Count how many days had >10% gain across all tickers
print("\n--- Days with >=10% gain ---")
count = 0
for t in tickers:
    df = f.get_data(t, "2025-06-22", "2026-06-22", "1d")
    if df.empty:
        continue
    pct = df["Close"].pct_change() * 100
    big = pct[pct >= 10.0]
    if not big.empty:
        for d, v in big.items():
            print(f"  {t:6s} {d}: +{v:.1f}%")
        count += len(big)
print(f"\nTotal >=10% days across {len(tickers)} stocks: {count}")
