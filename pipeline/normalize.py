"""
normalize.py — Merge all raw series into the columnar data.json + meta.json contract.

Pipeline of transforms (see DATA-CONTRACT.md):

  1. Load every raw CSV produced by the fetch_* modules + the FX and CPI series.
  2. Build a UNION daily date axis from START_DATE..today across all price series.
  3. Convert each series to VND:
       - US stocks / crypto / international metals : value(USD) x USD/VND (that day, ffilled)
       - VN stocks (vnstock)                       : value x 1000  (thousands VND -> VND)
       - VNINDEX                                   : index points, kept as-is (NOT VND)
       - VN gold SJC                               : already VND (bid + ask kept separately)
       - ROS (manual CSV)                          : already VND
  4. Forward-fill each series on the union axis; values before an asset's first
     real observation stay null (asset not yet listed).
  5. Round every VND price to an integer.
  6. SAVINGS : synthetic index of 1 VND compounding daily at config annual_rate.
  7. CPI     : annual World Bank index interpolated to a daily deflator (NOT VND).
  8. Emit data/processed/{data.json, meta.json} and copy both to web/data/.

For SJC (has_spread) we output BOTH:
       "SJC"      = bid  (giá mua vào) -> portfolio valuation
       "SJC__buy" = ask  (giá bán ra)  -> purchase price when DCAing
"""

import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import RAW_DIR, MANUAL_DIR, PROCESSED_DIR, WEB_DATA_DIR, get_logger
from config import ASSETS, FEES, PRESETS, START_DATE

log = get_logger("normalize")
END_DATE = pd.Timestamp.today().normalize()


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _load_close_csv(key: str) -> pd.Series | None:
    """Load data/raw/<key>.csv (Date,Close) as a Date-indexed Series."""
    path = RAW_DIR / f"{key}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["Date"])
    if "Close" not in df.columns or df.empty:
        return None
    s = df.set_index("Date")["Close"].sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s if not s.empty else None


def load_fx() -> pd.Series | None:
    """Load USD/VND series (Date-indexed)."""
    return _load_close_csv("USDVND")


def load_sjc() -> pd.DataFrame | None:
    """Load SJC raw (Date, buy_vnd, sell_vnd)."""
    path = RAW_DIR / "SJC.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["Date"])
    if df.empty or "buy_vnd" not in df.columns or "sell_vnd" not in df.columns:
        return None
    df = df.set_index("Date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df if not df.empty else None


def load_ros() -> pd.Series | None:
    """Load the manual ROS CSV (delisted ticker). Expected columns: date, close (VND)."""
    path = MANUAL_DIR / "ROS.csv"
    if not path.exists():
        log.warning("  ROS manual CSV missing — skipped")
        return None
    try:
        df = pd.read_csv(path)
        cols = {c.lower().strip(): c for c in df.columns}
        date_col = cols.get("date") or cols.get("time")
        close_col = cols.get("close") or cols.get("price")
        if not date_col or not close_col:
            log.warning("  ROS.csv present but missing date/close columns — skipped")
            return None
        s = (
            df[[date_col, close_col]]
            .rename(columns={date_col: "Date", close_col: "Close"})
            .assign(Date=lambda d: pd.to_datetime(d["Date"]))
            .set_index("Date")["Close"]
            .sort_index()
        )
        s = pd.to_numeric(s, errors="coerce").dropna()
        s = s[s > 0]
        s = s[~s.index.duplicated(keep="last")]
        log.info(f"  ROS manual CSV loaded: {len(s)} rows  {s.index[0].date()} -> {s.index[-1].date()}")
        return s if not s.empty else None
    except Exception as exc:
        log.warning(f"  ROS.csv could not be read ({exc}) — skipped")
        return None


# ---------------------------------------------------------------------------
# Synthetic / macro series
# ---------------------------------------------------------------------------
def build_savings(axis: pd.DatetimeIndex, annual_rate: float) -> pd.Series:
    """1 VND growing at annual_rate, compounded daily, expressed in VND.

    Uses an actual/365 day-count from the first axis date.
    """
    base = 1_000_000.0  # start the index at 1,000,000 VND for readable magnitudes
    daily = (1.0 + annual_rate) ** (1.0 / 365.0)
    days = (axis - axis[0]).days.to_numpy(dtype=float)
    values = base * (daily ** days)
    return pd.Series(values, index=axis)


def build_cpi_daily(axis: pd.DatetimeIndex) -> pd.Series | None:
    """Interpolate annual World Bank CPI to a daily index across the axis.

    Annual values are anchored at mid-year (Jul 1) and linearly interpolated;
    the tail (years not yet published) is held flat at the last known value.
    Returned as an index/deflator (NOT VND), rounded to a few decimals.
    """
    path = RAW_DIR / "CPI.csv"
    if not path.exists():
        log.warning("  CPI.csv missing — CPI series skipped")
        return None
    df = pd.read_csv(path)
    if "Year" not in df.columns or "CPI" not in df.columns or df.empty:
        log.warning("  CPI.csv malformed — CPI series skipped")
        return None

    df = df.sort_values("Year")
    # Anchor each annual figure at mid-year.
    anchor_dates = pd.to_datetime(df["Year"].astype(str) + "-07-01")
    anchor = pd.Series(df["CPI"].to_numpy(dtype=float), index=anchor_dates).sort_index()

    # Reindex onto union of axis + anchors, interpolate by time, then restrict to axis.
    combined_index = anchor.index.union(axis)
    s = anchor.reindex(combined_index).interpolate(method="time")
    # Hold flat before first / after last anchor.
    s = s.ffill().bfill()
    s = s.reindex(axis)
    return s


# ---------------------------------------------------------------------------
# Main normalize routine
# ---------------------------------------------------------------------------
def normalize() -> dict:
    """Build and persist data.json + meta.json. Returns a per-asset status dict."""
    status: dict[str, dict] = {}

    # ---- Load shared series -------------------------------------------------
    fx = load_fx()
    if fx is None:
        log.error("  USD/VND FX series missing! USD-denominated assets cannot be converted.")
    sjc = load_sjc()
    ros = load_ros()

    # ---- Gather raw price series per asset ---------------------------------
    # raw_series[key] = (Series in NATIVE units, native_currency_is_usd: bool)
    raw_series: dict[str, pd.Series] = {}
    first_dates: dict[str, pd.Timestamp] = {}
    last_dates: dict[str, pd.Timestamp] = {}   # last real observation (for delisting detection)

    for key, meta in ASSETS.items():
        source = meta.get("source")
        try:
            if source == "yfinance":
                s = _load_close_csv(key)            # USD (stocks/crypto/index)
            elif source == "stooq":
                s = _load_close_csv(key)            # USD per ounce
            elif source == "vnstock":
                s = _load_close_csv(key)            # thousands VND (stock) or points (index)
            elif source == "cafef_sjc":
                s = sjc["buy_vnd"] if sjc is not None else None  # VND bid
            elif source == "manual":
                s = ros if key == "ROS" else None   # VND
            else:
                # computed (SAVINGS) / worldbank (CPI) handled separately later
                s = None
            raw_series[key] = s
            if s is not None and not s.empty:
                first_dates[key] = s.index.min()
                last_dates[key] = s.index.max()
        except Exception as exc:
            log.error(f"  {key}: failed to stage raw series ({exc})")
            raw_series[key] = None

    # ---- Build the union daily date axis -----------------------------------
    # Every calendar day from START_DATE..today (forward-fill makes weekends/holidays
    # carry the last trade; this gives a dense, simulator-friendly axis).
    axis = pd.date_range(start=START_DATE, end=END_DATE, freq="D")
    log.info(f"  union axis: {len(axis)} days  {axis[0].date()} -> {axis[-1].date()}")

    # FX forward-filled onto the axis (for USD -> VND conversion).
    fx_daily = None
    if fx is not None:
        fx_daily = fx.reindex(fx.index.union(axis)).ffill().reindex(axis)
        # Back-fill any leading gap (FX history may start a day or two late) so the
        # earliest USD observations are still convertible.
        fx_daily = fx_daily.bfill()

    # ---- Assemble the output series dict -----------------------------------
    out_series: dict[str, list] = {}

    USD_SOURCES = {"yfinance", "stooq"}

    for key, meta in ASSETS.items():
        source = meta.get("source")
        a_type = meta.get("type")

        # SAVINGS and CPI are synthesised after the loop.
        if source in ("computed", "worldbank"):
            continue

        s = raw_series.get(key)
        if s is None or s.empty:
            status[key] = dict(ok=False, rows=0, start=None, end=None, note="no data")
            continue

        # 1) Reindex onto axis with forward-fill (no back-fill: pre-listing stays NaN).
        aligned = s.reindex(s.index.union(axis)).ffill().reindex(axis)
        # Null-before-listing: anything strictly before the first real date is NaN.
        aligned[axis < first_dates[key]] = np.nan
        # Null-after-delisting: if the last real trade is well before today (>30d), the
        # ticker is delisted (e.g. ROS, 2022) — null the tail so DCA stops buying at
        # delisting and we don't fake a flat price line to the present.
        last = last_dates.get(key)
        if last is not None and last < (END_DATE - pd.Timedelta(days=30)):
            aligned[axis > last] = np.nan

        # 2) Unit / currency conversion.
        if source in USD_SOURCES:
            if fx_daily is None:
                status[key] = dict(ok=False, rows=0, start=None, end=None, note="no FX to convert USD")
                continue
            aligned = aligned * fx_daily            # USD -> VND
        elif source == "vnstock":
            if a_type == "index":
                pass                                # VNINDEX: keep index points as-is
            else:
                aligned = aligned * 1000.0          # thousands VND -> VND
        # cafef_sjc / manual are already VND -> no scaling.

        # 3) Round VND prices to integers (indices keep as-is but are still rounded
        #    to whole numbers for compact JSON; VNINDEX points rounded to int too).
        out_series[key] = _to_json_list(aligned, round_int=True)

        valid = aligned.dropna()
        status[key] = dict(
            ok=True,
            rows=int(valid.shape[0]),
            start=str(first_dates[key].date()),
            end=str(valid.index.max().date()) if not valid.empty else None,
            note=source,
        )

        # 4) SJC second leg (ask / giá bán ra) -> "<KEY>__buy".
        if meta.get("has_spread") and source == "cafef_sjc" and sjc is not None:
            ask = sjc["sell_vnd"]
            ask_aligned = ask.reindex(ask.index.union(axis)).ffill().reindex(axis)
            ask_aligned[axis < first_dates[key]] = np.nan
            out_series[f"{key}__buy"] = _to_json_list(ask_aligned, round_int=True)
            log.info(f"  {key}: emitted bid (SJC) + ask (SJC__buy)")

    # ---- SAVINGS (computed) ------------------------------------------------
    if "SAVINGS" in ASSETS:
        rate = ASSETS["SAVINGS"].get("annual_rate", 0.06)
        savings = build_savings(axis, rate)
        out_series["SAVINGS"] = _to_json_list(savings, round_int=True)
        status["SAVINGS"] = dict(ok=True, rows=len(axis), start=str(axis[0].date()),
                                 end=str(axis[-1].date()), note=f"computed {rate:.0%}/yr")
        first_dates["SAVINGS"] = axis[0]

    # ---- CPI (worldbank) ---------------------------------------------------
    if "CPI" in ASSETS:
        cpi = build_cpi_daily(axis)
        if cpi is not None:
            # CPI is a deflator index: keep 3 decimals, do NOT treat as VND.
            out_series["CPI"] = _to_json_list(cpi, round_int=False, decimals=3)
            valid = cpi.dropna()
            status["CPI"] = dict(ok=True, rows=int(valid.shape[0]),
                                 start=str(valid.index.min().date()) if not valid.empty else None,
                                 end=str(valid.index.max().date()) if not valid.empty else None,
                                 note="worldbank CPI (daily-interp)")
            first_dates["CPI"] = axis[0]
        else:
            status["CPI"] = dict(ok=False, rows=0, start=None, end=None, note="no CPI")

    # ---- Write data.json ---------------------------------------------------
    data_obj = {
        "dates": [d.strftime("%Y-%m-%d") for d in axis],
        "series": out_series,
    }
    _write_json(PROCESSED_DIR / "data.json", data_obj)

    # ---- Build + write meta.json ------------------------------------------
    meta_obj = build_meta(first_dates)
    _write_json(PROCESSED_DIR / "meta.json", meta_obj)

    # ---- Copy both to web/data/ -------------------------------------------
    _write_json(WEB_DATA_DIR / "data.json", data_obj)
    _write_json(WEB_DATA_DIR / "meta.json", meta_obj)

    return status


def build_meta(first_dates: dict) -> dict:
    """Assemble meta.json from the ASSETS registry + actual first dates."""
    assets_meta = {}
    for key, meta in ASSETS.items():
        fd = first_dates.get(key)
        assets_meta[key] = {
            "name": meta.get("name", key),
            "market": meta.get("market"),
            "type": meta.get("type"),
            "source": meta.get("source"),
            "tier": meta.get("tier"),
            "first_date": str(fd.date()) if isinstance(fd, pd.Timestamp) else None,
            "has_spread": bool(meta.get("has_spread", False)),
        }
    return {
        "generated_at": pd.Timestamp.today().strftime("%Y-%m-%d"),
        "base_currency": "VND",
        "assets": assets_meta,
        "presets": PRESETS,
        "fees": FEES,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_json_list(series: pd.Series, round_int: bool, decimals: int = 0) -> list:
    """Convert a Series to a JSON-safe list: NaN -> None, numbers rounded.

    round_int=True  -> Python ints (or None)
    round_int=False -> floats rounded to `decimals` (or None)
    """
    out = []
    if round_int:
        for v in series.to_numpy():
            if v is None or (isinstance(v, float) and np.isnan(v)):
                out.append(None)
            else:
                out.append(int(round(float(v))))
    else:
        for v in series.to_numpy():
            if v is None or (isinstance(v, float) and np.isnan(v)):
                out.append(None)
            else:
                out.append(round(float(v), decimals))
    return out


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    size_kb = path.stat().st_size / 1024
    log.info(f"  wrote {path}  ({size_kb:,.1f} KB)")


if __name__ == "__main__":
    st = normalize()
    ok = sum(1 for v in st.values() if v.get("ok"))
    log.info(f"normalize complete: {ok}/{len(st)} series OK")
