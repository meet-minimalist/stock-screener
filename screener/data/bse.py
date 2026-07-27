"""Build and cache the *BSE-exclusive* ticker list.

The India fundamentals universe is keyed off NSE (the Nifty Total Market index).
Some genuinely investable companies are listed **only** on the BSE, never on the
NSE — NSDL, Benares Hotels, Automobile Corp of Goa, Andrew Yule, … — and those are
missing entirely. This module finds them and caches them for reuse.

Approach (one network call per source, so it's cheap to refresh monthly):

1. **BSE** publishes every active equity scrip via a JSON API, each row carrying
   its numeric scrip code, ``scrip_id`` (the readable ticker), ISIN, trading group
   and market cap.
2. **NSE** publishes its full equity list (``EQUITY_L.csv``) with ISINs.
3. A stock is *BSE-exclusive* when its ISIN is on BSE but **not** on NSE. We keep
   the mainboard equity groups (A/B/X/XT) above a market-cap floor — dropping the
   SME boards, the surveillance/non-compliant groups, ETFs/funds and the penny tail.

The result is written to ``data/tickers/bse_only.csv`` and reused until the next
refresh. screener.in resolves these companies by their **numeric scrip code**
(their ``scrip_id`` often 404s), so the cache carries both: ``Symbol`` (the
readable ticker we key records by) and ``ScripCode`` (the screener.in slug).
"""

from __future__ import annotations

import io
import logging

import pandas as pd
import requests

from screener.paths import TICKERS_DIR

logger = logging.getLogger(__name__)

BSE_ONLY_CACHE = TICKERS_DIR / "bse_only.csv"
NSE_EQUITY_CACHE = TICKERS_DIR / "nse_equity_full.csv"

# BSE's "List of Scrips" JSON feed — all active equity scrips in one response.
_BSE_SCRIP_API = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"
# NSE's full equity listing (the whole exchange, not just an index).
_NSE_EQUITY_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}

# Mainboard equity groups. A/B are the liquid mainboard; X/XT are the same board's
# lower-liquidity catch-all (where most legitimate small/microcaps sit). Excluded by
# default: M*/IP (SME platform, thinner disclosure), T/TS (trade-to-trade
# surveillance), Z/ZP (non-compliant) and P/Y/R (periodic/illiquid) — different-risk
# segments, not just low liquidity. A market-cap floor then trims the penny tail.
_DEFAULT_GROUPS = ("A", "B", "X", "XT")
_MIN_MKTCAP = 100.0     # ₹ crore; drops sub-floor shells (and no-market-cap rows)

# Columns of the cached BSE-only list.
_COLUMNS = ["Symbol", "ScripCode", "Company Name", "Industry", "ISIN Code", "Group", "MktCap", "YF"]


def _ensure_dir() -> None:
    TICKERS_DIR.mkdir(parents=True, exist_ok=True)


def fetch_bse_scrips() -> pd.DataFrame:
    """All active BSE equity scrips (scrip code, id, ISIN, group, market cap)."""
    resp = requests.get(
        _BSE_SCRIP_API,
        headers={**_HEADERS, "Accept": "application/json",
                 "Referer": "https://www.bseindia.com/corporates/List_Scrips.html"},
        params={"Group": "", "Scripcode": "", "industry": "",
                "segment": "Equity", "status": "Active"},
        timeout=60,
    )
    resp.raise_for_status()
    df = pd.DataFrame(resp.json())
    logger.info("Fetched %d active BSE equity scrips", len(df))
    return df


def fetch_nse_isins(force_refresh: bool = False) -> set[str]:
    """ISINs of every NSE-listed equity (full ``EQUITY_L`` list, cached).

    NSE gates non-browser clients, so we prime a cookie against the homepage first
    and fall back to the committed cache if the live fetch is unavailable.
    """
    if NSE_EQUITY_CACHE.exists() and not force_refresh:
        df = pd.read_csv(NSE_EQUITY_CACHE)
    else:
        session = requests.Session()
        session.headers.update(_HEADERS)
        try:
            session.get("https://www.nseindia.com", timeout=30)  # prime cookies
        except requests.RequestException:
            pass
        resp = session.get(_NSE_EQUITY_URL, timeout=60)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]
        _ensure_dir()
        df.to_csv(NSE_EQUITY_CACHE, index=False)
        logger.info("Cached %d NSE equity ISINs", len(df))
    col = next((c for c in ("ISIN NUMBER", "ISIN Code", "ISIN") if c in df.columns), None)
    if col is None:
        raise ValueError(f"No ISIN column in NSE equity list; got {list(df.columns)}")
    return set(df[col].astype(str).str.strip())


def _bse_only(bse: pd.DataFrame, nse_isins: set[str],
              groups: tuple[str, ...] = _DEFAULT_GROUPS,
              min_mktcap: float = _MIN_MKTCAP) -> pd.DataFrame:
    """Pure diff/filter: BSE scrips whose ISIN is absent from NSE, mainboard only.

    Keeps the requested trading ``groups`` at or above ``min_mktcap`` (₹ crore),
    drops ETFs/funds and malformed ISINs, and de-duplicates on ISIN then
    ``scrip_id`` (keeping the largest cap of a clash). A row with no market cap
    fails the floor and is dropped.
    """
    df = bse.copy()
    df["ISIN_NUMBER"] = df["ISIN_NUMBER"].astype(str).str.strip().str.upper()
    df["scrip_id"] = df["scrip_id"].astype(str).str.strip().str.upper()
    df["GROUP"] = df["GROUP"].astype(str).str.strip().str.upper()
    df["Mktcap"] = pd.to_numeric(df["Mktcap"], errors="coerce")

    # ``INE`` prefixes equity shares; ``INF`` is mutual-fund/ETF units and ``IN0/IN9``
    # are debt — the BSE equity segment lists all three, but only INE names are the
    # operating companies a fundamentals screener wants.
    df = df[df["ISIN_NUMBER"].str.fullmatch(r"INE[0-9A-Z]{9}")]
    df = df[df["scrip_id"].ne("") & df["scrip_id"].ne("NAN")]
    df = df[df["GROUP"].isin([g.upper() for g in groups])]
    df = df[df["Mktcap"] >= min_mktcap]                          # trims the penny tail
    df = df[~df["ISIN_NUMBER"].isin(nse_isins)]                  # BSE-exclusive
    df = df[~df["Scrip_Name"].astype(str)
            .str.contains("ETF|FUND|Issue Price", case=False, na=False)]

    df = df.sort_values("Mktcap", ascending=False, na_position="last")
    df = df.drop_duplicates(subset="ISIN_NUMBER", keep="first")
    df = df.drop_duplicates(subset="scrip_id", keep="first")

    out = pd.DataFrame({
        "Symbol": df["scrip_id"],
        "ScripCode": df["SCRIP_CD"].astype(str).str.strip(),
        "Company Name": df["Scrip_Name"].astype(str).str.strip(),
        "Industry": df["INDUSTRY"],
        "ISIN Code": df["ISIN_NUMBER"],
        "Group": df["GROUP"],
        "MktCap": df["Mktcap"],
    })
    out["YF"] = out["Symbol"] + ".BO"          # yfinance / yf_cache symbol
    return out[_COLUMNS].sort_values("Symbol").reset_index(drop=True)


def refresh_bse_only(force_refresh: bool = False,
                     groups: tuple[str, ...] = _DEFAULT_GROUPS,
                     min_mktcap: float = _MIN_MKTCAP) -> pd.DataFrame:
    """Rebuild ``bse_only.csv`` from the live BSE + NSE sources and cache it."""
    out = _bse_only(fetch_bse_scrips(), fetch_nse_isins(force_refresh), groups, min_mktcap)
    _ensure_dir()
    out.to_csv(BSE_ONLY_CACHE, index=False)
    logger.info("Wrote %d BSE-exclusive names to %s", len(out), BSE_ONLY_CACHE)
    return out


def load_bse_only(refresh: bool = False) -> pd.DataFrame:
    """Return the cached BSE-exclusive list, building it once if missing.

    Never raises on a network hiccup — an unavailable source yields an empty frame
    so the India pipeline degrades to its NSE universe rather than failing.
    """
    if BSE_ONLY_CACHE.exists() and not refresh:
        return pd.read_csv(BSE_ONLY_CACHE, dtype={"ScripCode": str})
    try:
        return refresh_bse_only(force_refresh=refresh)
    except Exception as exc:  # noqa: BLE001 - optional universe, never fatal
        logger.warning("BSE-only universe unavailable (%s); continuing without it", exc)
        return pd.DataFrame(columns=_COLUMNS)


def _clean_sector(value: object) -> str | None:
    s = str(value).strip()
    return s if s and s.lower() not in ("nan", "none") else None


def india_extra_universe() -> tuple[list[str], dict[str, str], dict[str, str | None]]:
    """BSE-exclusive names for the India fundamentals fetch.

    Returns ``(tickers, aliases, sectors)`` where records key on ``Symbol`` (the
    readable BSE ticker), ``aliases`` maps each to its numeric screener.in slug, and
    ``sectors`` carries BSE's industry where present (often blank for these names).
    """
    df = load_bse_only()
    if df.empty:
        return [], {}, {}
    symbols = df["Symbol"].astype(str).tolist()
    aliases = dict(zip(symbols, df["ScripCode"].astype(str)))
    sectors = {sym: _clean_sector(ind) for sym, ind in zip(symbols, df["Industry"])}
    return symbols, aliases, sectors


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build the BSE-exclusive ticker list")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-fetch the NSE equity list too (not just BSE)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s | %(message)s")

    out = refresh_bse_only(force_refresh=args.refresh)
    print(f"BSE-exclusive names: {len(out)} -> {BSE_ONLY_CACHE}")
    print(out[["Symbol", "Company Name", "Group", "MktCap"]].head(10).to_string(index=False))


if __name__ == "__main__":
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    main()
