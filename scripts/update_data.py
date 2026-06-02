"""
update_data.py — Orchestrate the full data pipeline.

Runs every fetch_* module, then normalize.py, and prints a per-ticker summary
(rows, date range, OK/FAIL). Each stage is isolated so a failure in one source
never aborts the others. The local run is the canonical data source for the app.

Usage:
    "C:\\Program Files\\Python312\\python.exe" D:\\Stock\\scripts\\update_data.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

from _util import get_logger  # noqa: E402  (also enforces UTF-8 stdout)
import fetch_us
import fetch_metals
import fetch_vn
import fetch_sjc
import fetch_fx
import fetch_macro
import normalize

log = get_logger("update_data")


def _run_stage(name: str, fn) -> dict:
    """Run one fetch stage, catching everything so the pipeline always continues."""
    log.info("=" * 70)
    log.info(f"STAGE: {name}")
    log.info("=" * 70)
    t0 = time.time()
    try:
        res = fn()
        dt = time.time() - t0
        log.info(f"  {name} finished in {dt:0.1f}s")
        return res or {}
    except Exception as exc:
        log.error(f"  {name} stage CRASHED (handled): {exc}")
        return {}


def main() -> int:
    overall_t0 = time.time()

    fetched: dict = {}
    fetched.update(_run_stage("fetch_fx (USD/VND)", fetch_fx.run))
    fetched.update(_run_stage("fetch_us (yfinance)", fetch_us.run))
    fetched.update(_run_stage("fetch_metals (gold/silver)", fetch_metals.run))
    fetched.update(_run_stage("fetch_vn (vnstock)", fetch_vn.run))
    fetched.update(_run_stage("fetch_sjc (SJC gold)", fetch_sjc.run))
    fetched.update(_run_stage("fetch_macro (CPI)", fetch_macro.run))

    # ---- Normalize ---------------------------------------------------------
    log.info("=" * 70)
    log.info("STAGE: normalize")
    log.info("=" * 70)
    try:
        status = normalize.normalize()
    except Exception as exc:
        log.error(f"  normalize CRASHED: {exc}")
        status = {}

    # ---- Per-ticker summary ------------------------------------------------
    log.info("=" * 70)
    log.info("PER-TICKER SUMMARY")
    log.info("=" * 70)
    log.info(f"{'KEY':<10}{'STATUS':<8}{'ROWS':>7}  {'FIRST':<12}{'LAST':<12}{'NOTE'}")
    log.info("-" * 70)

    n_ok = 0
    for key in status:
        st = status[key]
        flag = "OK" if st.get("ok") else "FAIL"
        if st.get("ok"):
            n_ok += 1
        log.info(
            f"{key:<10}{flag:<8}{st.get('rows', 0):>7}  "
            f"{str(st.get('start') or '-'):<12}{str(st.get('end') or '-'):<12}{st.get('note', '')}"
        )

    log.info("-" * 70)
    log.info(f"TOTAL: {n_ok}/{len(status)} series OK")
    log.info(f"Pipeline finished in {time.time() - overall_t0:0.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
