"""
Tahap 4-5: analisa harga + perhitungan selisih.

Mengubah hasil scraping menjadi kolom-kolom analisa pada Main Data:
  Marketplace, Nama Produk Marketplace, Link Produk,
  Harga Marketplace Termurah, Harga Marketplace Rata-rata,
  Selisih Harga, Persentase Selisih, Status Harga, Tanggal Cek.

Perhitungan (acuan = harga marketplace TERMURAH, benchmark paling ketat):
  Selisih   = Harga Marketplace Termurah - Harga Main Data
  Persentase= Selisih / Harga Marketplace Termurah * 100
Status:
  Harga Main Data < Termurah -> "Lebih Murah" (hijau)
  Harga Main Data = Termurah -> "Sama"        (kuning)
  Harga Main Data > Termurah -> "Lebih Mahal" (merah)
  tanpa data marketplace     -> "No Data"
"""
from __future__ import annotations

import re
from datetime import date
from statistics import mean, median

import numpy as np
import pandas as pd

from scraper.base import Candidate, ProductQuery

from . import cleaner, config
from .logger import get_logger

log = get_logger()


def _row_getter(master: pd.DataFrame):
    """Bikin fungsi pembaca nilai kolom kanonik dari sebuah baris."""
    roles = cleaner.resolve_roles(list(master.columns))

    def get(row, role):
        col = roles.get(role)
        if not col:
            return None
        val = row.get(col)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return str(val)

    return get


# Satuan jual / kemasan yang bikin pencarian terlalu spesifik -> dibuang dari
# keyword (tetap tersimpan di data asli, hanya tidak dikirim ke marketplace).
_SATUAN_JUAL_RE = re.compile(
    r"\bper\s+(pcs|pc|set|zak|sak|pail|roll|lembar|lbr|unit|box|dus|kaleng|klg|"
    r"galon|gln|batang|btg|meter|mtr|pack|pak|bag|karung|krg|buah|biji|butir|"
    r"lusin|rim|sheet|ea)\b",
    re.IGNORECASE,
)


def _clean_search_terms(text: str) -> str:
    """Rapikan keyword agar tidak terlalu spesifik: buang koma, satuan jual, dash."""
    text = text.replace(",", " ")
    text = _SATUAN_JUAL_RE.sub(" ", text)        # buang "Per Pcs / Per Zak" dst.
    text = re.sub(r"\s[-–—]\s", " ", text)        # buang dash pemisah " - "
    text = re.sub(r"\s+", " ", text).strip()
    # Batasi panjang agar pencarian tetap luas (ambil ~10 kata pertama).
    words = text.split(" ")
    if len(words) > 10:
        text = " ".join(words[:10])
    return text


def make_search_keyword(
    name, brand=None, variant=None, barcode=None
) -> str:
    """
    Bentuk keyword pencarian marketplace yang sudah dinormalisasi + dibersihkan.

    Nama produk dibersihkan dari [PO]/[READY]/prefix status; lalu keyword akhir
    dibuang koma & satuan jual ("Per Pcs" dst.) supaya pencarian tidak nihil.
    Barcode tetap diprioritaskan bila tersedia (paling akurat).
    """
    if barcode:
        return str(barcode).strip()
    base = cleaner.normalize_keyword(name) or ""
    parts = [base]
    for extra in (brand, variant):
        if extra:
            parts.append(str(extra).strip())
    return _clean_search_terms(" ".join(p for p in parts if p).strip())


def build_queries(master: pd.DataFrame) -> list[ProductQuery]:
    """Susun ProductQuery dari tiap baris master untuk dikirim ke scraper."""
    get = _row_getter(master)

    queries: list[ProductQuery] = []
    for idx, row in master.iterrows():
        raw_name = get(row, "product_name")
        if not raw_name:
            continue
        # Normalisasi keyword: nama untuk matching sudah bersih dari [PO]/prefix,
        # sedangkan search_override adalah keyword final (tanpa koma/satuan jual)
        # yang benar-benar dikirim ke marketplace agar hasil lebih banyak.
        name = cleaner.normalize_keyword(raw_name) or raw_name
        brand = get(row, "brand")
        variant = get(row, "variant")
        barcode = get(row, "barcode")
        main_price = row.get(config.MAIN_PRICE_COLUMN)
        queries.append(
            ProductQuery(
                index=int(idx),
                name=name,
                brand=brand,
                sku=get(row, "sku"),
                barcode=barcode,
                variant=variant,
                main_price=float(main_price) if pd.notna(main_price) else None,
                search_override=make_search_keyword(raw_name, brand, variant, barcode),
            )
        )
    return queries


def add_search_keyword_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tambah kolom "Search Keyword" (keyword setelah dibersihkan) tepat setelah
    kolom nama produk. Selalu terisi untuk semua baris, terlepas dari apakah
    scraping dijalankan atau tidak.
    """
    get = _row_getter(df)
    roles = cleaner.resolve_roles(list(df.columns))

    keywords = [
        make_search_keyword(
            get(row, "product_name"),
            get(row, "brand"),
            get(row, "variant"),
            get(row, "barcode"),
        )
        for _, row in df.iterrows()
    ]

    if config.SEARCH_KEYWORD_COLUMN in df.columns:
        df[config.SEARCH_KEYWORD_COLUMN] = keywords
        return df

    # Sisipkan tepat setelah kolom nama produk agar mudah dibaca.
    name_col = roles.get("product_name")
    pos = (df.columns.get_loc(name_col) + 1) if name_col in df.columns else df.shape[1]
    df.insert(pos, config.SEARCH_KEYWORD_COLUMN, keywords)
    return df


def _drop_low_outliers(cands: list[Candidate]) -> list[Candidate]:
    """
    Buang kandidat dengan harga tak wajar murah (aksesori, sampel, salah satuan)
    yang bisa membuat "termurah" menyesatkan.

    Cara: bandingkan terhadap MEDIAN harga kandidat. Yang di bawah
    median x PRICE_OUTLIER_FLOOR dianggap outlier dan dibuang. Hanya berlaku
    bila kandidat cukup banyak (>=4) supaya median bermakna.
    """
    priced = [c for c in cands if c.price and c.price > 0]
    if len(priced) < 3:
        return priced
    med = median(c.price for c in priced)
    floor = med * config.PRICE_OUTLIER_FLOOR
    kept = [c for c in priced if c.price >= floor]
    return kept or priced


def _summarize_candidates(cands: list[Candidate]) -> dict:
    """Ringkas kandidat: harga termurah, rata-rata, dan sumber termurah."""
    # Saring dulu outlier murah (lintas semua kandidat, sebelum ambil termurah).
    filtered = _drop_low_outliers(cands)

    # Ambil harga termurah per marketplace supaya rata-rata tidak bias ke satu toko.
    by_mp: dict[str, Candidate] = {}
    for c in filtered:
        if c.price is None or c.price <= 0:
            continue
        cur = by_mp.get(c.marketplace)
        if cur is None or c.price < cur.price:
            by_mp[c.marketplace] = c

    if not by_mp:
        return {}

    prices = [c.price for c in by_mp.values()]
    cheapest = min(by_mp.values(), key=lambda c: c.price)
    return {
        "cheapest": cheapest,
        "termurah": cheapest.price,
        "rata_rata": round(mean(prices), 2),
    }


def analyze(master: pd.DataFrame, scrape_results: dict[int, list[Candidate]]) -> pd.DataFrame:
    """Isi kolom analisa harga pada master DataFrame."""
    log.info("Comparing prices...")
    df = master.copy()
    today = date.today().isoformat()

    # Keyword pencarian ternormalisasi (dipakai saat scraping) ikut dilaporkan.
    df = add_search_keyword_column(df)

    # Siapkan kolom kosong dulu (urutan sesuai config).
    for col in config.ANALYSIS_COLUMNS:
        df[col] = None

    n_cheaper = n_equal = n_expensive = n_nodata = 0

    for idx in df.index:
        cands = scrape_results.get(int(idx), [])
        main_price = df.at[idx, config.MAIN_PRICE_COLUMN]
        summary = _summarize_candidates(cands)

        if not summary:
            # Tahap 12: tidak ditemukan -> No Data, proses tetap lanjut.
            df.at[idx, "Marketplace"] = "Not Found"
            df.at[idx, "Status Harga"] = config.STATUS_NO_DATA
            df.at[idx, "Tanggal Cek"] = today
            n_nodata += 1
            continue

        cheapest: Candidate = summary["cheapest"]
        termurah = summary["termurah"]
        df.at[idx, "Marketplace"] = cheapest.marketplace
        df.at[idx, "Nama Produk Marketplace"] = cheapest.title
        df.at[idx, "Link Produk"] = cheapest.url
        df.at[idx, "Harga Marketplace Termurah"] = termurah
        df.at[idx, "Harga Marketplace Rata-rata"] = summary["rata_rata"]
        df.at[idx, "Tanggal Cek"] = today

        # Perhitungan selisih hanya bila harga kita tersedia.
        if pd.isna(main_price):
            df.at[idx, "Status Harga"] = config.STATUS_NO_DATA
            n_nodata += 1
            continue

        main_price = float(main_price)
        selisih = termurah - main_price
        df.at[idx, "Selisih Harga"] = selisih
        df.at[idx, "Persentase Selisih"] = (
            round(selisih / termurah * 100, 2) if termurah else None
        )

        if main_price < termurah:
            df.at[idx, "Status Harga"] = config.STATUS_CHEAPER
            n_cheaper += 1
        elif main_price > termurah:
            df.at[idx, "Status Harga"] = config.STATUS_MORE_EXPENSIVE
            n_expensive += 1
        else:
            df.at[idx, "Status Harga"] = config.STATUS_EQUAL
            n_equal += 1

    log.info(
        "  Hasil: %d lebih murah, %d sama, %d lebih mahal, %d tanpa data.",
        n_cheaper,
        n_equal,
        n_expensive,
        n_nodata,
    )
    return df


def build_summary(df: pd.DataFrame) -> dict:
    """Kumpulkan angka ringkasan untuk sheet Summary (Tahap 7)."""
    total = len(df)
    status = df["Status Harga"]
    cheaper = int((status == config.STATUS_CHEAPER).sum())
    equal = int((status == config.STATUS_EQUAL).sum())
    expensive = int((status == config.STATUS_MORE_EXPENSIVE).sum())
    no_data = int((status == config.STATUS_NO_DATA).sum())

    selisih = pd.to_numeric(df["Selisih Harga"], errors="coerce")
    avg_selisih = float(selisih.mean()) if selisih.notna().any() else 0.0

    # Marketplace yang paling sering jadi harga termurah.
    mp = df.loc[df["Status Harga"] != config.STATUS_NO_DATA, "Marketplace"]
    mp = mp[mp.notna() & (mp != "Not Found")]
    top_mp = mp.value_counts().idxmax() if not mp.empty else "-"

    return {
        "Total Produk": total,
        "Produk Lebih Murah": cheaper,
        "Produk Sama": equal,
        "Produk Lebih Mahal": expensive,
        "Produk Tanpa Data Marketplace": no_data,
        "Rata-rata Selisih Harga": round(avg_selisih, 2),
        "Marketplace Termurah Terbanyak": top_mp,
    }
