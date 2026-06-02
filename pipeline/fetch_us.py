"""
fetch_us.py — Fetch US stocks, ETFs, crypto, and indices from yfinance.

Covers every ASSETS entry with source=="yfinance" (including BTC-USD, ^GSPC).
Uses auto_adjust=True so Close = Adjusted Close (total return: splits + dividends).
Saves raw CSV to data/raw/<KEY>.csv (columns: Date,Close).
Per-ticker try/except: logs failure and continues — one failure never kills the run.
"""

import sys
from pathlib import Path
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAW_DIR, get_logger
from config import ASSETS, START_DATE

log = get_logger("fetch_us")
END_DATE = pd.Timestamp.today().strftime("%Y-%m-%d")


def fetch_ticker(key: str, ticker: str, min_date: str | None = None) -> pd.DataFrame | None:
    """Download daily history from yfinance; return DataFrame indexed by Date with a Close column.

    auto_adjust=True -> Close is the split/dividend-adjusted price (total return).
    multi_level_index=False -> flat single-level columns for a single ticker.
    min_date -> drop any rows before this date. Used when a ticker symbol was
    recycled from a predecessor (e.g. DJT carries DWAC SPAC history before its
    2024-03-26 listing), so only the true post-listing series is kept.
    """
    log.info(f"  fetching {key} ({ticker}) ...")
    df = yf.download(
        ticker,
        start=START_DATE,
        end=END_DATE,
        auto_adjust=True,
        progress=False,
        multi_level_index=False,
    )
    if df is None or df.empty or "Close" not in df.columns:
        log.warning(f"  {key}: empty / malformed response from yfinance")
        return None

    df = df[["Close"]].copy()
    df.index = pd.to_datetime(df.index).normalize()
    df.index.name = "Date"
    df = df.dropna(subset=["Close"])
    df = df[df["Close"] > 0]
    df = df.sort_index()
    # Collapse any accidental duplicate dates, keeping the last observation.
    df = df[~df.index.duplicated(keep="last")]
    # Clip predecessor-ticker history (e.g. DJT's pre-2024 DWAC data).
    if min_date:
        df = df[df.index >= pd.to_datetime(min_date)]
    if df.empty:
        return None
    return df


def run() -> dict:
    """Fetch all yfinance assets. Returns {key: DataFrame or None}."""
    targets = {k: v for k, v in ASSETS.items() if v.get("source") == "yfinance"}
    results: dict = {}

    for key, meta in targets.items():
        ticker = meta["ticker"]
        try:
            df = fetch_ticker(key, ticker, min_date=meta.get("min_date"))
            if df is not None:
                out_path = RAW_DIR / f"{key}.csv"
                df.to_csv(out_path)
                log.info(f"  {key}: {len(df)} rows  {df.index[0].date()} -> {df.index[-1].date()}  saved")
                results[key] = df
            else:
                results[key] = None
        except Exception as exc:
            log.error(f"  {key} FAILED: {exc}")
            results[key] = None

    return results


if __name__ == "__main__":
    run()
