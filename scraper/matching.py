"""
Mesin pencocokan relevansi (Tahap 3 - pemilihan hasil).

Memberi skor 0-100 pada tiap Candidate terhadap ProductQuery, dengan urutan
kepentingan sesuai spec:
    1. SKU
    2. Barcode
    3. Nama produk
    4. Merk
    5. Ukuran / Volume

Aturan penting: JANGAN membandingkan produk yang beda ukuran/spesifikasi.
Bila ukuran pada query dan kandidat sama-sama terdeteksi tapi berbeda,
kandidat langsung didiskualifikasi (skor 0).
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from .base import Candidate, ProductQuery

# Token ukuran/volume: angka + satuan umum konstruksi & retail Indonesia.
_SIZE_UNIT = r"(?:mm|cm|m|inch|inci|in|ft|kaki|kg|gr?|gram|ml|l|liter|watt|w|volt|v|pcs|lembar|roll|meter)"
_SIZE_RE = re.compile(rf"(\d+(?:[.,]\d+)?)\s*({_SIZE_UNIT})\b", re.IGNORECASE)
# Pola dimensi seperti 4x8, 60x60, 18x180.
_DIM_RE = re.compile(r"\b(\d+(?:[.,]\d+)?(?:\s*[x×]\s*\d+(?:[.,]\d+)?)+)\b", re.IGNORECASE)


def extract_size_tokens(*texts: str | None) -> set[str]:
    """Ambil himpunan token ukuran/dimensi ternormalisasi dari sejumlah teks."""
    tokens: set[str] = set()
    for text in texts:
        if not text:
            continue
        low = text.lower()
        for num, unit in _SIZE_RE.findall(low):
            tokens.add(f"{num.replace(',', '.')}{unit.lower()}")
        for dim in _DIM_RE.findall(low):
            tokens.add(re.sub(r"\s*", "", dim).replace("×", "x").replace(",", "."))
    return tokens


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def score_candidate(query: ProductQuery, cand: Candidate) -> float:
    """
    Hitung skor relevansi 0-100. Semakin tinggi semakin cocok.

    Bobot: SKU/barcode exact = dominan; sisanya dari kemiripan nama + merk.
    """
    title = _norm(cand.title)
    if not title:
        return 0.0

    # --- Diskualifikasi berdasarkan ukuran (guard spesifikasi) ---
    q_sizes = extract_size_tokens(query.name, query.variant)
    c_sizes = extract_size_tokens(cand.title)
    if q_sizes and c_sizes and not (q_sizes & c_sizes):
        # Dua-duanya menyebut ukuran, tapi tidak ada yang beririsan -> beda barang.
        return 0.0

    # --- 1 & 2: SKU / Barcode exact match (sinyal terkuat) ---
    if query.barcode and query.barcode.lower() in title:
        return 100.0
    if query.sku and len(query.sku) >= 4 and query.sku.lower() in title:
        return 98.0

    # --- 3: Nama produk (token set ratio tahan urutan kata) ---
    name_score = fuzz.token_set_ratio(_norm(query.name), title)

    # --- 4: Merk (bonus bila muncul di judul) ---
    brand_bonus = 0.0
    if query.brand and _norm(query.brand) and _norm(query.brand) in title:
        brand_bonus = 5.0

    # --- 5: Ukuran cocok (bonus bila ada irisan ukuran) ---
    size_bonus = 5.0 if (q_sizes and (q_sizes & c_sizes)) else 0.0

    return min(100.0, name_score + brand_bonus + size_bonus)


def rank(query: ProductQuery, candidates: list[Candidate], threshold: float) -> list[Candidate]:
    """Beri skor, buang di bawah ambang, urutkan dari paling relevan."""
    scored: list[Candidate] = []
    for c in candidates:
        c.score = score_candidate(query, c)
        if c.score >= threshold and c.price is not None and c.price > 0:
            scored.append(c)
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored
