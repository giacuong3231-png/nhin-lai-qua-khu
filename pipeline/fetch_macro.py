"""
fetch_macro.py — Fetch Vietnam CPI (inflation index) from the World Bank API.

Indicator FP.CPI.TOTL, country VN, annual frequency. The World Bank publishes
this as an index (2010 = 100 base in the current series). It is used as a
deflator to compute real (inflation-adjusted) returns in the frontend, so the
absolute base does not matter — only year-over-year ratios do.

normalize.py interpolates these annual points to a daily curve.

Saves raw CSV to data/raw/CPI.csv (columns: Year,CPI).
"""

import sys
from pathlib import Path
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAW_DIR, get_logger

log = get_logger("fetch_macro")

WB_URL = (
    "https://api.worldbank.org/v2/country/VN/indicator/FP.CPI.TOTL"
    "?format=json&per_page=500"
)
OUT_KEY = "CPI"


def fetch_cpi() -> pd.DataFrame | None:
    """Download annual CPI for Vietnam. Returns DataFrame indexed by Year (int)."""
    log.info("  fetching VN CPI (World Bank FP.CPI.TOTL) ...")
    resp = requests.get(WB_URL, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        log.error("  CPI: unexpected World Bank response shape")
        return None

    rows = [
        {"Year": int(d["date"]), "CPI": float(d["value"])}
        for d in payload[1]
        if d.get("value") is not None
    ]
    if not rows:
        return None

    df = pd.DataFrame(rows).sort_values("Year").set_index("Year")
    return df


def run() -> dict:
    """Fetch VN CPI. Returns {"CPI": DataFrame or None}."""
    try:
        df = fetch_cpi()
        if df is not None and not df.empty:
            out_path = RAW_DIR / f"{OUT_KEY}.csv"
            df.to_csv(out_path)
            log.info(f"  {OUT_KEY}: {len(df)} annual points  "
                     f"{df.index[0]} -> {df.index[-1]}  saved")
            return {OUT_KEY: df}
        log.error(f"  {OUT_KEY}: empty response")
    except Exception as exc:
        log.error(f"  {OUT_KEY} FAILED: {exc}")
    return {OUT_KEY: None}


if __name__ == "__main__":
    run()
