"""
fetch_fx.py — Fetch the USD/VND daily exchange rate from yfinance ("USDVND=X").

This rate converts every non-VND series (US stocks, crypto, international metals)
into VND inside normalize.py. The interbank rate is used as-is; a configurable
usd_vnd_spread (see config.FEES) is applied at simulation time, not here.

Saves raw CSV to data/raw/USDVND.csv (columns: Date,Close).
"""

import sys
from pathlib import Path
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAW_DIR, get_logger
from config import START_DATE

log = get_logger("fetch_fx")
END_DATE = pd.Timestamp.today().strftime("%Y-%m-%d")

FX_TICKER = "USDVND=X"
OUT_KEY = "USDVND"


def fetch_fx() -> pd.DataFrame | None:
    """Download USD/VND daily close from yfinance."""
    log.info(f"  fetching {OUT_KEY} ({FX_TICKER}) ...")
    df = yf.download(
        FX_TICKER,
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
    # Guard against junk: USD/VND should be in the thousands (~20k-30k).
    df = df[(df["Close"] > 1000) & (df["Close"] < 100000)]
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df if not df.empty else None


def run() -> dict:
    """Fetch USD/VND. Returns {"USDVND": DataFrame or None}."""
    try:
        df = fetch_fx()
        if df is not None:
            out_path = RAW_DIR / f"{OUT_KEY}.csv"
            df.to_csv(out_path)
            log.info(f"  {OUT_KEY}: {len(df)} rows  {df.index[0].date()} -> {df.index[-1].date()}  "
                     f"(first={df['Close'].iloc[0]:.0f}, last={df['Close'].iloc[-1]:.0f})  saved")
            return {OUT_KEY: df}
        log.error(f"  {OUT_KEY}: empty response from yfinance")
    except Exception as exc:
        log.error(f"  {OUT_KEY} FAILED: {exc}")
    return {OUT_KEY: None}


if __name__ == "__main__":
    run()
