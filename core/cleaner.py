"""
Tahap 2 (cleaning): dilakukan per-DataFrame sebelum digabung.

- Hapus baris kosong
- Rapikan teks (hilangkan spasi berlebih, trim)
- Rapikan nama produk
- Samakan format harga menjadi numerik
- Samakan format SKU / barcode
- Hapus duplicate
- Encoding aman (semua teks dinormalkan ke str)
"""
from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

from . import config
from .logger import get_logger

log = get_logger()

_WS_RE = re.compile(r"\s+")
# Ambil angka dari string harga, tahan terhadap "Rp", titik/koma ribuan, spasi.
_NON_NUMERIC_RE = re.compile(r"[^0-9,.\-]")

# --- Normalisasi keyword pencarian marketplace ---
# 1) Buang seluruh blok dalam tanda siku, mis. "[PO]", "[READY]".
_KW_BRACKET_RE = re.compile(r"\[[^\]]*\]")
# 2) Buang prefix status stok/pesanan yang tersisa DI AWAL nama (boleh berulang,
#    mis. "PO PROMO Cat"). \b memastikan kata utuh: "POLES" tidak ikut terpotong.
_KW_PREFIX_RE = re.compile(
    r"^(?:\s*(?:PRE[\s\-]?ORDER|PO|READY|STOCK|INDENT|PROMO|NEW)\b[\s:,\-–—]*)+",
    re.IGNORECASE,
)


def normalize_keyword(value) -> str | None:
    """
    Bersihkan nama produk menjadi keyword pencarian marketplace.

    Aturan:
      - Hapus semua teks di dalam tanda siku []      -> "[PO] Sika 25Kg" -> "Sika 25Kg"
      - Hapus prefix sisa: PO / PRE ORDER / PRE-ORDER / READY / STOCK /
        INDENT / PROMO / NEW (hanya bila berada di awal)
      - Rapikan spasi berlebih

    Yang TIDAK dihapus: brand, variant, ukuran, volume, warna, nomor seri.
    Prefix hanya dibuang di awal, jadi mis. "Cat Avian NEW 5Kg" tetap utuh.

    Mengembalikan None bila input kosong; bila hasil pembersihan jadi kosong
    (mis. nama hanya "[PO]"), nama asli yang sudah dirapikan dikembalikan agar
    pencarian tidak kehilangan keyword sama sekali.
    """
    text = clean_text(value)
    if text is None:
        return None

    cleaned = _KW_BRACKET_RE.sub(" ", text)
    cleaned = _KW_PREFIX_RE.sub("", cleaned)
    cleaned = _WS_RE.sub(" ", cleaned).strip()

    # Jangan pernah kembalikan keyword kosong -> fallback ke nama asli.
    return cleaned or text


def _canonical_lookup(columns: list[str]) -> dict[str, str]:
    """
    Petakan peran kanonik -> nama kolom nyata pada DataFrame ini.

    Contoh hasil: {"product_name": "name", "sku": "sku", ...}
    Hanya peran yang benar-benar ada yang dimasukkan.
    """
    lower_map = {str(c).strip().lower(): c for c in columns}
    resolved: dict[str, str] = {}
    for role, aliases in config.COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower_map:
                resolved[role] = lower_map[alias]
                break
    return resolved


def clean_text(value) -> str | None:
    """Normalkan satu nilai teks: unicode NFC, trim, spasi tunggal."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value)
    # Normalisasi unicode supaya encoding aman & konsisten.
    text = unicodedata.normalize("NFC", text)
    text = _WS_RE.sub(" ", text).strip()
    return text or None


def parse_price(value) -> float | None:
    """
    Ubah beragam format harga menjadi float.

    Menangani: 250000, "250000", "Rp 250.000", "1,250,000.50", "Rp250.000,-".
    Mengembalikan None bila tidak ada angka yang valid.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if (isinstance(value, float) and np.isnan(value)) else float(value)

    text = _NON_NUMERIC_RE.sub("", str(value)).strip().strip("-")
    if not text:
        return None

    # Tentukan pemisah desimal berdasarkan simbol terakhir.
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            # Format Indonesia/EU: titik ribuan, koma desimal -> 1.250.000,50
            text = text.replace(".", "").replace(",", ".")
        else:
            # Format US: koma ribuan, titik desimal -> 1,250,000.50
            text = text.replace(",", "")
    elif "," in text:
        # Hanya koma: anggap ribuan (harga IDR jarang pakai desimal).
        text = text.replace(",", "")
    else:
        # Hanya titik. Jika terlihat seperti ribuan (mis. 250.000), buang titik.
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
            text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


def normalize_sku(value) -> str | None:
    """Samakan format SKU/barcode: string, tanpa '.0', uppercase, trim."""
    text = clean_text(value)
    if text is None:
        return None
    # Angka yang terbaca sebagai float (1051.0) -> "1051".
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".")[0]
    return text.upper()


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Bersihkan satu DataFrame hasil pembacaan file."""
    if df.empty:
        return df

    df = df.copy()
    roles = _canonical_lookup(list(df.columns))
    before = len(df)

    # 1) Normalisasi semua kolom teks (object) -> trim + spasi tunggal + unicode.
    meta_cols = {config.SOURCE_FILE_COLUMN}
    for col in df.columns:
        if col in meta_cols:
            continue
        if df[col].dtype == object:
            df[col] = df[col].map(clean_text)

    # 2) Rapikan nama produk (kolom kanonik product_name).
    if "product_name" in roles:
        name_col = roles["product_name"]
        df[name_col] = df[name_col].map(clean_text)

    # 3) Harga -> numerik untuk semua kandidat kolom harga yang ada.
    price_cols_present = [
        c for c in df.columns if str(c).strip().lower() in config.PRICE_SOURCE_COLUMNS
    ]
    for col in price_cols_present:
        df[col] = df[col].map(parse_price)

    # 4) SKU / barcode -> format seragam.
    for role in ("sku", "barcode"):
        if role in roles:
            df[roles[role]] = df[roles[role]].map(normalize_sku)

    # 5) Hapus baris yang benar-benar kosong (mengabaikan kolom meta Source File).
    data_cols = [c for c in df.columns if c not in meta_cols]
    df = df.dropna(axis=0, how="all", subset=data_cols)

    # 6) Buang baris tanpa nama produk (data tidak berguna untuk analisa).
    if "product_name" in roles:
        df = df[df[roles["product_name"]].notna()]

    # 7) Hapus duplicate (berdasarkan kolom data, bukan Source File).
    df = df.drop_duplicates(subset=data_cols, keep="first")

    after = len(df)
    log.info("  Cleaning: %d -> %d baris (dibuang %d)", before, after, before - after)
    return df.reset_index(drop=True)


def clean_all(frames: list[pd.DataFrame]) -> list[pd.DataFrame]:
    """Bersihkan setiap DataFrame dalam daftar."""
    log.info("Cleaning data...")
    return [clean_dataframe(df) for df in frames if not df.empty]


# Diekspor supaya modul lain (merger/analyzer) bisa menemukan kolom kanonik.
def resolve_roles(columns: list[str]) -> dict[str, str]:
    return _canonical_lookup(columns)
