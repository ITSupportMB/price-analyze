"""
Logging terpusat: tampil ke console sekaligus tersimpan ke file di logs/.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime

from . import config


_CONFIGURED = False


def setup_logger(name: str = "price_analyzer", level: int = logging.INFO) -> logging.Logger:
    """
    Konfigurasi root logger sekali saja. Aman dipanggil berkali-kali.

    Output:
      - Console (stdout) dengan format ringkas.
      - File logs/run_YYYYMMDD_HHMMSS.log dengan format lengkap.
    """
    global _CONFIGURED
    logger = logging.getLogger(name)

    if _CONFIGURED:
        return logger

    config.ensure_dirs()
    logger.setLevel(level)
    logger.propagate = False

    # Handler console
    console = logging.StreamHandler(stream=sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S"))
    logger.addHandler(console)

    # Handler file
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = config.LOGS_DIR / f"run_{stamp}.log"
    fileh = logging.FileHandler(logfile, encoding="utf-8")
    fileh.setLevel(logging.DEBUG)
    fileh.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    )
    logger.addHandler(fileh)

    _CONFIGURED = True
    logger.debug("Logger siap. File log: %s", logfile)
    return logger


def get_logger(name: str = "price_analyzer") -> logging.Logger:
    """Ambil logger yang sudah dikonfigurasi (atau konfigurasi bila belum)."""
    if not _CONFIGURED:
        return setup_logger(name)
    return logging.getLogger(name)
