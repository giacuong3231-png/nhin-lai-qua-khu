"""
fetch_vn.py — Fetch Vietnamese stocks and VN-Index via vnstock v4 (VCI source).

Fetches ADJUSTED daily prices (dividends + bonus shares + splits already baked in).
Uses the modern `vnstock.api.quote.Quote` interface (the legacy `Vnstock()` class is
deprecated and spams banners). All vnstock stdout chatter is silenced via _util.

UNITS (important):
  * Stocks  : vnstock returns price in THOUSANDS of VND (e.g. 74.8 -> 74,800 VND).
  * VNINDEX : vnstock returns INDEX POINTS (e.g. 1826.47), NOT thousands.
  Raw CSVs here keep the NATIVE vnstock value. The thousands->VND scaling for
  stocks is applied centrally in normalize.py (which knows each asset's type),
  so the raw files stay faithful to the source.

Per-ticker try/except: logs failure and continues.
Saves raw CSV to data/raw/<KEY>.csv (columns: Date,Close).
"""

import sys
import time
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAW_DIR, get_logger, silence_stdout
from config import ASSETS, START_DATE

log = get_logger("fetch_vn")
END_DATE = pd.Timestamp.today().strftime("%Y-%m-%d")


def _normalize_history(df: pd.DataFrame) -> pd.DataFrame | None:
    """Coerce a vnstock history frame to a clean Date-indexed Close frame."""
    if df is None or df.empty:
        return None
    df = df.copy()
    # vnstock columns are lowercase: time, open, high, low, close, volume
    if "time" in df.columns:
        df = df.rename(columns={"time": "Date"})
    elif "date" in df.columns:
        df = df.rename(columns={"date": "Date"})
    if "close" in df.columns:
        df = df.rename(columns={"close": "Close"})
    if "Date" not in df.columns or "Close" not in df.columns:
        return None
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")[["Close"]].dropna()
    df = df[df["Close"] > 0].sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df if not df.empty else None


def _history(symbol: str, source: str = "VCI") -> pd.DataFrame | None:
    """Call vnstock Quote.history with banners silenced."""
    with silence_stdout():
        from vnstock.api.quote import Quote
        q = Quote(symbol=symbol, source=source)
        df = q.history(start=START_DATE, end=END_DATE, interval="1D")
    return _normalize_history(df)


def fetch_stock(key: str, ticker: str) -> pd.DataFrame | None:
    """Fetch one VN stock's adjusted daily history from VCI."""
    log.info(f"  fetching {key} ({ticker}) ...")
    return _history(ticker, source="VCI")


def fetch_vnindex() -> pd.DataFrame | None:
    """Fetch VN-Index. VCI is the reliable source for the index symbol."""
    for source in ("VCI",):  # valid sources: kbs, vci, msn, dnse, binance, fmp, fmarket
        try:
            log.info(f"  fetching VNINDEX (source={source}) ...")
            df = _history("VNINDEX", source=source)
            if df is not None:
                return df
        except Exception as exc:
            log.warning(f"  VNINDEX source={source} failed: {exc}")
    return None


def run() -> dict:
    """Fetch all vnstock assets. Returns {key: DataFrame or None}."""
    targets = {k: v for k, v in ASSETS.items() if v.get("source") == "vnstock"}
    results: dict = {}

    for key, meta in targets.items():
        ticker = meta["ticker"]
        try:
            if ticker == "VNINDEX":
                df = fetch_vnindex()
            else:
                df = fetch_stock(key, ticker)

            if df is not None:
                out_path = RAW_DIR / f"{key}.csv"
                df.to_csv(out_path)
                log.info(f"  {key}: {len(df)} rows  {df.index[0].date()} -> {df.index[-1].date()}  saved")
                results[key] = df
            else:
                log.warning(f"  {key}: empty response — skipped")
                results[key] = None

            time.sleep(0.4)  # be polite to the API
        except Exception as exc:
            log.error(f"  {key} FAILED: {exc}")
            results[key] = None

    return results


if __name__ == "__main__":
    run()
