"""
fetch_metals.py — Fetch international gold (XAUUSD) and silver (XAGUSD) spot prices.

Primary source : Stooq CSV download (https://stooq.com/q/d/l/?s=xauusd&i=d).
Fallback       : yfinance GC=F (gold futures) / SI=F (silver futures).

NOTE: Stooq now gates raw CSV downloads behind an API key for many clients
(the response body starts with "Get your apikey"). When that happens we detect
it and transparently fall back to yfinance, which tracks spot closely.

Output is in USD per ounce (converted to VND later in normalize.py).
Saves raw CSV to data/raw/<KEY>.csv (columns: Date,Close).
"""

import sys
from io import StringIO
from pathlib import Path
import pandas as pd
import requests
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAW_DIR, get_logger
from config import START_DATE

log = get_logger("fetch_metals")
END_DATE = pd.Timestamp.today().strftime("%Y-%m-%d")

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&d1={d1}&d2={d2}&i=d"

# asset key -> (stooq_symbol, yfinance_fallback_ticker)
METAL_SOURCES = {
    "XAUUSD": ("xauusd", "GC=F"),
    "XAGUSD": ("xagusd", "SI=F"),
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def fetch_stooq(symbol: str) -> pd.DataFrame | None:
    """Download CSV from Stooq. Returns DataFrame (Date index, Close col) or None."""
    d1 = START_DATE.replace("-", "")
    d2 = END_DATE.replace("-", "")
    url = STOOQ_URL.format(symbol=symbol, d1=d1, d2=d2)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        text = resp.text
        # Stooq returns a plain-text apikey notice instead of CSV when gated.
        if not text.lstrip().lower().startswith("date"):
            log.warning(f"  Stooq did not return CSV for {symbol} (likely apikey-gated)")
            return None
        df = pd.read_csv(StringIO(text))
        if df.empty or "Close" not in df.columns:
            return None
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")[["Close"]].dropna()
        df = df[df["Close"] > 0].sort_index()
        return df if not df.empty else None
    except Exception as exc:
        log.warning(f"  Stooq fetch failed for {symbol}: {exc}")
        return None


def fetch_yfinance_fallback(ticker: str) -> pd.DataFrame | None:
    """Fallback: fetch metal futures via yfinance (tracks spot closely)."""
    log.info(f"  yfinance fallback: {ticker}")
    try:
        df = yf.download(
            ticker,
            start=START_DATE,
            end=END_DATE,
            auto_adjust=True,
            progress=False,
            multi_level_index=False,
        )
        if df is None or df.empty or "Close" not in df.columns:
            return None
        df = df[["Close"]].copy()
        df.index = pd.to_datetime(df.index).normalize()
        df.index.name = "Date"
        df = df.dropna(subset=["Close"])
        df = df[df["Close"] > 0].sort_index()
        df = df[~df.index.duplicated(keep="last")]
        return df if not df.empty else None
    except Exception as exc:
        log.warning(f"  yfinance fallback failed for {ticker}: {exc}")
        return None


def run() -> dict:
    """Fetch XAUUSD and XAGUSD. Returns {key: DataFrame or None}."""
    results: dict = {}

    for key, (stooq_sym, yf_ticker) in METAL_SOURCES.items():
        log.info(f"fetching {key} ...")
        df = None
        try:
            df = fetch_stooq(stooq_sym)
            if df is not None and len(df) > 100:
                log.info(f"  {key} (Stooq): {len(df)} rows  {df.index[0].date()} -> {df.index[-1].date()}")
            else:
                log.warning(f"  Stooq insufficient for {key}, trying yfinance fallback ...")
                df = fetch_yfinance_fallback(yf_ticker)
                if df is not None:
                    log.info(f"  {key} (yfinance): {len(df)} rows  {df.index[0].date()} -> {df.index[-1].date()}")
                else:
                    log.error(f"  {key}: BOTH Stooq and yfinance failed!")
        except Exception as exc:
            log.error(f"  {key} FAILED: {exc}")
            df = None

        results[key] = df
        if df is not None:
            out_path = RAW_DIR / f"{key}.csv"
            df.to_csv(out_path)
            log.info(f"  {key}: saved -> {out_path.name}")

    return results


if __name__ == "__main__":
    run()
