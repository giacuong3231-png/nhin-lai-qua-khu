"""
_util.py — Shared helpers for the data pipeline.

Centralises:
  * project paths (ROOT, RAW_DIR, PROCESSED_DIR, WEB_DATA_DIR)
  * logging configuration
  * UTF-8 stdout enforcement (vnstock + Vietnamese tickers print non-ASCII)
  * a context manager that silences vnstock's noisy promotional banners
"""

import sys
import io
import logging
import contextlib
from pathlib import Path

# ---------------------------------------------------------------------------
# Force UTF-8 on stdout/stderr.
# vnstock and Vietnamese asset names contain characters that crash the default
# Windows cp1252 console encoding. Reconfigure the streams once, on import.
# ---------------------------------------------------------------------------
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
MANUAL_DIR = RAW_DIR / "manual"
PROCESSED_DIR = ROOT / "data" / "processed"
WEB_DATA_DIR = ROOT / "web" / "data"

for _d in (RAW_DIR, MANUAL_DIR, PROCESSED_DIR, WEB_DATA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-7s %(message)s",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# vnstock banner suppression
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def silence_stdout():
    """Temporarily redirect stdout to swallow vnstock's promo/deprecation banners.

    stderr is left intact so genuine warnings still surface.
    """
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        yield
    finally:
        sys.stdout = old
