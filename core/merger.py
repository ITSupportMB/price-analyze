"""
Tahap 1 (gabung): menyatukan seluruh DataFrame yang sudah bersih menjadi
satu "Main Data Product".

- Kolom disesuaikan berdasarkan nama (union kolom, tidak ada data hilang).
- Menambah kolom Source File (sudah ada dari reader) + Import Date.
- Menentukan kolom kanonik "Harga Main Data" dari prioritas sumber harga.
- Menghapus duplicate lintas file.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from . import cleaner, config
from .logger import get_logger

log = get_logger()


def _pick_main_price(row: pd.Series, price_cols: list[str]) -> float | None:
    """Ambil harga pertama yang > 0 sesuai urutan prioritas kolom harga."""
    for col in price_cols:
        val = row.get(col)
        if val is not None and not (isinstance(val, float) and np.isnan(val)) and float(val) > 0:
            return float(val)
    # Bila semua 0/None, pakai nilai non-null pertama (walau 0) supaya tetap terisi.
    for col in price_cols:
        val = row.get(col)
        if val is not None and not (isinstance(val, float) and np.isnan(val)):
            return float(val)
    return None


def merge_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Gabungkan daftar DataFrame bersih menjadi satu master DataFrame."""
    if not frames:
        log.warning("Tidak ada data untuk digabung.")
        return pd.DataFrame()

    log.info("Merging data...")
    # concat menyelaraskan kolom berdasarkan nama; kolom yang tidak ada -> NaN.
    master = pd.concat(frames, ignore_index=True, sort=False)
    log.info("  Gabungan awal: %d baris, %d kolom", len(master), master.shape[1])

    # Import Date (Tahap 1).
    master[config.IMPORT_DATE_COLUMN] = date.today().isoformat()

    # Tentukan kolom "Harga Main Data" MENGIKUTI urutan prioritas di config
    # (bukan urutan kolom pada file). Prioritaskan harga JUAL, bukan harga beli.
    lower_to_actual = {str(c).strip().lower(): c for c in master.columns}
    price_cols = [
        lower_to_actual[name]
        for name in config.PRICE_SOURCE_COLUMNS
        if name in lower_to_actual
    ]
    if price_cols:
        master[config.MAIN_PRICE_COLUMN] = master.apply(
            lambda r: _pick_main_price(r, price_cols), axis=1
        )
        log.info("  Harga Main Data diambil dari prioritas: %s", ", ".join(price_cols))
    else:
        master[config.MAIN_PRICE_COLUMN] = np.nan
        log.warning("  Tidak ada kolom harga yang dikenali; Harga Main Data kosong.")

    # Dedupe lintas file (abaikan kolom meta saat membandingkan).
    ignore = {config.SOURCE_FILE_COLUMN, config.IMPORT_DATE_COLUMN}
    subset = [c for c in master.columns if c not in ignore]
    before = len(master)
    master = master.drop_duplicates(subset=subset, keep="first").reset_index(drop=True)
    if before != len(master):
        log.info("  Dedupe lintas file: %d -> %d baris", before, len(master))

    return _reorder_columns(master)


def _reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Susun kolom penting di depan agar laporan mudah dibaca."""
    roles = cleaner.resolve_roles(list(df.columns))
    front_roles = ["product_name", "brand", "sku", "barcode", "variant", "category", "uom"]
    front = [roles[r] for r in front_roles if r in roles]
    front += [config.MAIN_PRICE_COLUMN, config.SOURCE_FILE_COLUMN, config.IMPORT_DATE_COLUMN]

    seen: set = set()
    ordered: list = []
    for c in front:
        if c in df.columns and c not in seen:
            ordered.append(c)
            seen.add(c)
    for c in df.columns:
        if c not in seen:
            ordered.append(c)
            seen.add(c)
    return df[ordered]
