"""
fetch_ros_manual.py — one-off sourcing of ROS (FLC Faros) history for the manual store.

ROS was delisted from HOSE on 2022-09-05. The official live pipeline never calls an
API for ROS (config source="manual"); instead it reads data/raw/manual/ROS.csv.

This helper GENERATES that committed CSV. CafeF's old PriceHistory endpoint is dead,
but vnstock's VCI source still serves the full delisted history, so we use that here
and write it out as (date, close in VND) — the format normalize.py expects.

Run once:  python pipeline/fetch_ros_manual.py
"""
import csv
import os
import sys

HERE = os.path.dirname(__file__)
OUT = os.path.normpath(os.path.join(HERE, "..", "data", "raw", "manual", "ROS.csv"))


def fetch_ros():
    # vnstock 4.x unified API. VCI keeps history for delisted tickers.
    from vnstock.api.quote import Quote
    q = Quote(symbol="ROS", source="VCI")
    df = q.history(start="2016-09-01", end="2022-09-06", interval="1D")
    if df is None or df.empty:
        return None
    # Columns: time, open, high, low, close, volume. Prices are in THOUSAND-dong.
    df = df[["time", "close"]].copy()
    df["time"] = df["time"].astype(str).str.slice(0, 10)
    df = df[df["close"] > 0]
    return df


def main():
    df = fetch_ros()
    if df is None or df.empty:
        print("NO DATA for ROS — not sourced")
        sys.exit(1)

    rows = [(t, int(round(float(c) * 1000.0))) for t, c in zip(df["time"], df["close"])]
    rows = [(t, v) for t, v in rows if v > 0]
    rows.sort()
    print(f"parsed: {len(rows)} rows | range: {rows[0][0]} -> {rows[-1][0]}")
    print(f"min VND: {min(v for _, v in rows):,} | max VND: {max(v for _, v in rows):,}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "close"])
        w.writerows(rows)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
