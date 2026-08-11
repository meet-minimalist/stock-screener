"""Build and cache the India **SME** universe — kept entirely separate from the mainboard.

SME (small-and-medium-enterprise) platforms are a different market: large lot sizes,
thin liquidity, lighter disclosure and a higher manipulation rate. They must never mix
with mainboard filtration, so they live in their own universe and their own pages.

Two sources, one network call each (cheap to refresh monthly):

1. **NSE Emerge** — the SME board, published as ``SME_EQUITY_L.csv`` (series ``SM``/``ST``;
   ``SZ`` is suspended and dropped). Priced on yfinance with ``.NS``; screener.in resolves
   these by their NSE symbol.
2. **BSE SME** — trading groups ``M``/``MT``/``MS``/``IP`` of the BSE scrip list (reusing
   :func:`screener.data.bse.fetch_bse_scrips`). Priced ``SCRIPID.BO``; screener.in resolves
   these by their **numeric scrip code**.

The two are unioned on ISIN (NSE preferred on the rare dual listing) and written to
``data/tickers/india_sme.csv`` with everything the pipelines need: the record ``Symbol``,
the ``Exchange``, the screener.in ``ScripCode`` (BSE only) and the ``YF`` price symbol.
"""
from __future__ import annotations

import io
import logging

import pandas as pd
import requests

from screener.data.bse import _HEADERS, fetch_bse_scrips
from screener.paths import TICKERS_DIR

logger = logging.getLogger(__name__)

SME_CACHE = TICKERS_DIR / "india_sme.csv"

# NSE Emerge SME master list (archives host serves it directly, no cookie priming).
_NSE_SME_URL = "https://archives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv"
_NSE_KEEP_SERIES = ("SM", "ST")          # drop SZ (suspended)
_BSE_SME_GROUPS = ("M", "MT", "MS", "IP")

_COLUMNS = ["Symbol", "Exchange", "ScripCode", "Company Name", "ISIN Code", "Segment", "YF"]


def _ensure_dir() -> None:
    TICKERS_DIR.mkdir(parents=True, exist_ok=True)


def fetch_nse_sme() -> pd.DataFrame:
    """NSE Emerge SME constituents (Symbol / Name / Series / ISIN)."""
    resp = requests.get(_NSE_SME_URL, headers=_HEADERS, timeout=60)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = [c.strip() for c in df.columns]
    logger.info("Fetched %d NSE Emerge SME rows", len(df))
    return df


def _nse_sme_frame(raw: pd.DataFrame) -> pd.DataFrame:
    sym = next((c for c in raw.columns if c.upper() == "SYMBOL"), "SYMBOL")
    name = next((c for c in raw.columns if "NAME" in c.upper()), None)
    isin = next((c for c in raw.columns if "ISIN" in c.upper()), None)
    ser = next((c for c in raw.columns if c.upper() == "SERIES"), None)
    df = raw.copy()
    df["_sym"] = df[sym].astype(str).str.strip().str.upper()
    df["_isin"] = df[isin].astype(str).str.strip().str.upper() if isin else ""
    df["_ser"] = df[ser].astype(str).str.strip().str.upper() if ser else "SM"
    df = df[df["_ser"].isin(_NSE_KEEP_SERIES)]
    df = df[df["_isin"].str.fullmatch(r"INE[0-9A-Z]{9}")]
    return pd.DataFrame({
        "Symbol": df["_sym"],
        "Exchange": "NSE",
        "ScripCode": "",
        "Company Name": df[name].astype(str).str.strip() if name else df["_sym"],
        "ISIN Code": df["_isin"],
        "Segment": "NSE Emerge",
        "YF": df["_sym"] + ".NS",
    })


def _bse_sme_frame(bse: pd.DataFrame) -> pd.DataFrame:
    df = bse.copy()
    df["ISIN_NUMBER"] = df["ISIN_NUMBER"].astype(str).str.strip().str.upper()
    df["scrip_id"] = df["scrip_id"].astype(str).str.strip().str.upper()
    df["GROUP"] = df["GROUP"].astype(str).str.strip().str.upper()
    df = df[df["GROUP"].isin(_BSE_SME_GROUPS)]
    df = df[df["ISIN_NUMBER"].str.fullmatch(r"INE[0-9A-Z]{9}")]
    df = df[df["scrip_id"].ne("") & df["scrip_id"].ne("NAN")]
    return pd.DataFrame({
        "Symbol": df["scrip_id"],
        "Exchange": "BSE",
        "ScripCode": df["SCRIP_CD"].astype(str).str.strip(),
        "Company Name": df["Scrip_Name"].astype(str).str.strip(),
        "ISIN Code": df["ISIN_NUMBER"],
        "Segment": "BSE SME",
        "YF": df["scrip_id"] + ".BO",
    })


def _build(nse_raw: pd.DataFrame, bse_raw: pd.DataFrame) -> pd.DataFrame:
    """Union NSE Emerge + BSE SME, de-duplicated on ISIN (NSE wins a dual listing)."""
    frames = [f for f in (_nse_sme_frame(nse_raw), _bse_sme_frame(bse_raw)) if not f.empty]
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=_COLUMNS)
    out = out[out["Symbol"].astype(str).str.strip().ne("")]
    out = out.drop_duplicates(subset="ISIN Code", keep="first")   # NSE listed first -> kept
    out = out.drop_duplicates(subset="Symbol", keep="first")
    return out[_COLUMNS].sort_values(["Exchange", "Symbol"]).reset_index(drop=True)


def refresh_sme() -> pd.DataFrame:
    """Rebuild ``india_sme.csv`` from the live NSE Emerge + BSE SME sources."""
    out = _build(fetch_nse_sme(), fetch_bse_scrips())
    _ensure_dir()
    out.to_csv(SME_CACHE, index=False)
    logger.info("Wrote %d India SME names to %s", len(out), SME_CACHE)
    return out


def load_sme(refresh: bool = False) -> pd.DataFrame:
    """Cached SME universe, built once if missing; never raises on a network hiccup."""
    if SME_CACHE.exists() and not refresh:
        return pd.read_csv(SME_CACHE, dtype={"ScripCode": str})
    try:
        return refresh_sme()
    except Exception as exc:  # noqa: BLE001 - optional universe, never fatal
        logger.warning("India SME universe unavailable (%s); continuing without it", exc)
        return pd.DataFrame(columns=_COLUMNS)


def sme_universe() -> tuple[list[str], dict[str, str], dict[str, str | None]]:
    """``(tickers, aliases, sectors)`` for the SME fundamentals fetch.

    ``aliases`` maps a record ticker to its screener.in slug — the numeric scrip code
    for BSE SME names (NSE names resolve by their own symbol, so they need no alias).
    SME sources carry no sector, so ``sectors`` is empty.
    """
    df = load_sme()
    if df.empty:
        return [], {}, {}
    symbols = df["Symbol"].astype(str).tolist()
    aliases = {sym: str(code) for sym, code, exch in
               zip(symbols, df["ScripCode"], df["Exchange"]) if exch == "BSE" and str(code).strip()}
    return symbols, aliases, {}


def sme_price_universe() -> tuple[list[str], dict[str, str | None], dict[str, str]]:
    """``(tickers, sectors, price_symbols)`` for the SME technical pipeline.

    ``price_symbols`` maps each record ticker to its yfinance symbol — ``.NS`` for NSE
    Emerge names, ``SCRIPID.BO`` for BSE SME names.
    """
    df = load_sme()
    if df.empty:
        return [], {}, {}
    symbols = df["Symbol"].astype(str).tolist()
    price = dict(zip(symbols, df["YF"].astype(str)))
    return symbols, {}, price


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build the India SME ticker list")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    out = refresh_sme()
    print(f"India SME names: {len(out)} -> {SME_CACHE}")
    print(out["Exchange"].value_counts().to_dict())
    print(out[["Symbol", "Exchange", "Company Name"]].head(8).to_string(index=False))


if __name__ == "__main__":
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    main()
