"""
fetch_sjc.py — Fetch SJC gold daily history (BUY = giá mua vào, SELL = giá bán ra).

SJC gold has a bid/ask spread, so we keep BOTH legs:
    buy_vnd  = "giá mua vào"  (the shop BUYS gold from you / bid)  -> used to VALUE a holding
    sell_vnd = "giá bán ra"   (the shop SELLS gold to you / ask)  -> used to BUY when DCAing

Sources (in priority order), ALL wrapped in try/except so the pipeline never dies:

  1. SJC official API  (sjc.com.vn PriceService) — supports arbitrary historical
     windows of <=89 days. We page backwards from today to 2016 in 89-day chunks
     to assemble the full history. Values come back directly in VND.
        BuyValue  -> buy_vnd (bid)
        SellValue -> sell_vnd (ask)
  2. CafeF AJAX (cafef.vn) — only returns the most recent ~1 month, but is a
     useful fallback / top-up. buyPrice/sellPrice are in MILLIONS of VND.

Missing days are forward-filled (handled in normalize.py on the union axis).
Saves raw CSV to data/raw/SJC.csv (columns: Date,buy_vnd,sell_vnd).
"""

import sys
import time
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAW_DIR, get_logger
from config import START_DATE

log = get_logger("fetch_sjc")
END_DATE = pd.Timestamp.today().strftime("%Y-%m-%d")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://sjc.com.vn/",
}

SJC_API = "https://sjc.com.vn/GoldPrice/Services/PriceService.ashx"
CAFEF_API = "https://cafef.vn/du-lieu/Ajax/AjaxGoldPriceHistory.ashx"

# SJC "1 lượng" gold; the official API filters by this product name.
SJC_TYPE_KEYWORD = "1L"


def _parse_dotnet_date(s: str):
    """Parse a .NET '/Date(1779469200000)/' epoch-ms string to a pandas Timestamp (date only)."""
    try:
        ms = int(s.strip("/").replace("Date(", "").replace(")", "").split("+")[0].split("-")[0])
        return pd.to_datetime(ms, unit="ms").normalize()
    except Exception:
        return None


def fetch_sjc_official() -> pd.DataFrame | None:
    """Page the SJC official API backwards in 89-day windows to build full history.

    Returns DataFrame indexed by Date with buy_vnd, sell_vnd (VND), or None.
    """
    start = pd.to_datetime(START_DATE).date()
    today = date.today()
    window = timedelta(days=89)

    records: dict[pd.Timestamp, tuple[float, float]] = {}
    cur_to = today
    empty_streak = 0

    while cur_to >= start:
        cur_from = max(start, cur_to - window)
        try:
            resp = requests.post(
                SJC_API,
                headers=HEADERS,
                data={
                    "method": "GetGoldPriceHistory",
                    "goldPriceId": "1",
                    "fromDate": cur_from.strftime("%d/%m/%Y"),
                    "toDate": cur_to.strftime("%d/%m/%Y"),
                },
                timeout=30,
            )
            payload = resp.json()
        except Exception as exc:
            log.warning(f"  SJC official window {cur_from}..{cur_to} failed: {exc}")
            payload = None

        n_rows = 0
        if payload and payload.get("success") and isinstance(payload.get("data"), list):
            for row in payload["data"]:
                type_name = str(row.get("TypeName", ""))
                if SJC_TYPE_KEYWORD not in type_name:
                    continue
                d = _parse_dotnet_date(str(row.get("GroupDate", "")))
                if d is None:
                    continue
                buy = row.get("BuyValue")
                sell = row.get("SellValue")
                try:
                    buy = float(buy)
                    sell = float(sell)
                except (TypeError, ValueError):
                    continue
                if buy <= 0 or sell <= 0:
                    continue
                # Multiple intraday quotes per day. Within each API window rows
                # arrive OLDEST-first, so overwriting keeps the day's LAST (closing)
                # quote. Windows are walked newest->oldest and never overlap, so a
                # day is only ever populated from a single window.
                records[d] = (buy, sell)
                n_rows += 1

        if n_rows == 0:
            empty_streak += 1
            # If we hit several consecutive empty windows, history has run out.
            if empty_streak >= 3:
                log.info(f"  SJC official: history exhausted near {cur_to}")
                break
        else:
            empty_streak = 0

        cur_to = cur_from - timedelta(days=1)
        time.sleep(0.25)  # be polite

    if not records:
        return None

    df = pd.DataFrame(
        [(d, b, s) for d, (b, s) in records.items()],
        columns=["Date", "buy_vnd", "sell_vnd"],
    ).set_index("Date").sort_index()
    return df


def fetch_cafef() -> pd.DataFrame | None:
    """CafeF fallback: most recent ~1 month of SJC quotes. Prices in MILLIONS of VND."""
    try:
        resp = requests.get(CAFEF_API, headers=HEADERS, params={"index": "1"}, timeout=30)
        hist = resp.json().get("Data", {}).get("goldPriceWorldHistories") or []
    except Exception as exc:
        log.warning(f"  CafeF fallback failed: {exc}")
        return None

    rows = []
    for e in hist:
        if str(e.get("name", "")).upper() != "SJC":
            continue
        try:
            buy = float(e["buyPrice"]) * 1_000_000   # millions VND -> VND
            sell = float(e["sellPrice"]) * 1_000_000
            d = pd.to_datetime(e["createdAt"]).tz_localize(None).normalize()
        except Exception:
            continue
        if buy > 0 and sell > 0:
            rows.append((d, buy, sell))

    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["Date", "buy_vnd", "sell_vnd"])
    df = df.groupby("Date").last().sort_index()
    return df


def run() -> dict:
    """Fetch SJC history. Returns {"SJC": DataFrame or None}. Never raises."""
    df = None
    try:
        log.info("fetching SJC (official API, paged history) ...")
        df = fetch_sjc_official()
        if df is not None:
            log.info(f"  SJC official: {len(df)} days  {df.index[0].date()} -> {df.index[-1].date()}")
        else:
            log.warning("  SJC official returned no data — trying CafeF fallback")
    except Exception as exc:
        log.warning(f"  SJC official crashed (handled): {exc}")
        df = None

    # CafeF fallback / top-up for the most recent days.
    try:
        cafef = fetch_cafef()
        if cafef is not None:
            if df is None:
                df = cafef
                log.info(f"  SJC via CafeF fallback: {len(df)} days "
                         f"{df.index[0].date()} -> {df.index[-1].date()}")
            else:
                # Merge: official is authoritative; add any CafeF dates we lack.
                new = cafef[~cafef.index.isin(df.index)]
                if not new.empty:
                    df = pd.concat([df, new]).sort_index()
                    log.info(f"  SJC topped up with {len(new)} extra CafeF day(s)")
    except Exception as exc:
        log.warning(f"  SJC CafeF top-up crashed (handled): {exc}")

    if df is None or df.empty:
        log.warning("  SJC: NO data from any source — SJC will be skipped in normalize")
        return {"SJC": None}

    df = df[(df["buy_vnd"] > 0) & (df["sell_vnd"] > 0)]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    out_path = RAW_DIR / "SJC.csv"
    df.to_csv(out_path)
    log.info(f"  SJC: {len(df)} days total  {df.index[0].date()} -> {df.index[-1].date()}  saved")
    return {"SJC": df}


if __name__ == "__main__":
    run()
