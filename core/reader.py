"""
Tahap 1 (baca): membaca seluruh file produk (Excel / CSV) dari folder input.

Setiap file dibaca menjadi satu DataFrame, ditandai dengan nama file asalnya.
Encoding CSV ditangani secara aman (mencoba beberapa encoding umum).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config
from .logger import get_logger

log = get_logger()

# Urutan encoding yang dicoba untuk file CSV (paling umum lebih dulu).
_CSV_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]


def list_input_files(input_dir: Path | None = None) -> list[Path]:
    """Kumpulkan semua file produk yang didukung dari folder input."""
    input_dir = input_dir or config.INPUT_DIR
    if not input_dir.exists():
        log.warning("Folder input tidak ditemukan: %s", input_dir)
        return []

    files = sorted(
        p
        for p in input_dir.iterdir()
        if p.is_file()
        and p.suffix.lower() in config.SUPPORTED_EXTENSIONS
        and not p.name.startswith("~$")  # abaikan file lock Excel
    )
    return files


def _read_csv_safe(path: Path) -> pd.DataFrame:
    """Baca CSV dengan mencoba beberapa encoding sampai berhasil."""
    last_err: Exception | None = None
    for enc in _CSV_ENCODINGS:
        try:
            df = pd.read_csv(path, dtype=str, encoding=enc, keep_default_na=True)
            log.debug("CSV %s dibaca dengan encoding %s", path.name, enc)
            return df
        except (UnicodeDecodeError, UnicodeError) as exc:
            last_err = exc
            continue
    # Upaya terakhir: abaikan byte bermasalah supaya tidak ada data yang hilang total.
    log.warning("Encoding CSV %s bermasalah, fallback ke utf-8 errors='replace'", path.name)
    return pd.read_csv(path, dtype=str, encoding="utf-8", encoding_errors="replace")


def read_file(path: Path) -> pd.DataFrame | None:
    """
    Baca satu file produk menjadi DataFrame.

    Mengembalikan None bila file gagal dibaca (proses tetap lanjut ke file lain).
    Semua kolom dibaca apa adanya; konversi tipe dilakukan di tahap cleaning.
    """
    log.info("Reading %s...", path.name)
    try:
        if path.suffix.lower() == ".csv":
            df = _read_csv_safe(path)
        else:
            # Excel: baca semua sebagai objek supaya SKU/barcode tidak berubah
            # jadi float (mis. 1051 -> 1051.0) sebelum cleaning.
            df = pd.read_excel(path, dtype=object)
    except Exception as exc:  # noqa: BLE001 - sengaja luas: 1 file rusak != stop total
        log.error("Gagal membaca %s: %s", path.name, exc)
        return None

    if df.empty:
        log.warning("%s kosong / tanpa baris data.", path.name)
    else:
        log.info("  -> %d baris, %d kolom", len(df), df.shape[1])

    # Tandai asal file (dipakai lagi saat merge).
    df[config.SOURCE_FILE_COLUMN] = path.name
    return df


def read_all(input_dir: Path | None = None) -> list[pd.DataFrame]:
    """Baca semua file input, kembalikan daftar DataFrame (skip yang gagal)."""
    files = list_input_files(input_dir)
    if not files:
        log.warning("Tidak ada file produk pada folder input.")
        return []

    frames: list[pd.DataFrame] = []
    for path in files:
        df = read_file(path)
        if df is not None and not df.empty:
            frames.append(df)
    log.info("Total %d file berhasil dibaca.", len(frames))
    return frames
