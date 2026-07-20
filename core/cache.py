"""
Checkpoint / cache hasil scraping marketplace.

Tujuan: scraping bisa dilakukan BERTAHAP (batch) lintas beberapa sesi tanpa
mengulang produk yang sudah berhasil. Tokopedia memblokir bila terlalu banyak
request dalam satu sesi, jadi pendekatan yang realistis adalah mencicil.

Aturan cache:
  - Hanya hasil BERISI (ada kandidat) yang disimpan.
  - Produk yang gagal / kosong / terblokir TIDAK disimpan -> otomatis diretry
    pada sesi berikutnya.
  - Key per produk stabil lintas run: SKU bila ada, kalau tidak hash dari
    nama+varian. Jadi tidak bergantung pada urutan baris.

File: cache/marketplace_cache.json
"""
from __future__ import annotations

import hashlib
import json

from scraper.base import Candidate, ProductQuery

from . import config
from .logger import get_logger

log = get_logger()

CACHE_DIR = config.PROJECT_ROOT / "cache"
CACHE_FILE = CACHE_DIR / "marketplace_cache.json"


def product_key(sku, name, variant) -> str:
    """Key identitas produk yang stabil lintas run."""
    if sku and str(sku).strip():
        return "sku:" + str(sku).strip().upper()
    base = (str(name or "") + "|" + str(variant or "")).strip().lower()
    return "nv:" + hashlib.md5(base.encode("utf-8")).hexdigest()[:16]


def query_key(q: ProductQuery) -> str:
    return product_key(q.sku, q.name, q.variant)


def load_cache() -> dict:
    """Muat cache dari disk (kosong bila belum ada / rusak)."""
    if not CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("Cache tidak terbaca (%s); mulai dari kosong.", exc)
        return {}


def save_cache(cache: dict) -> None:
    """Simpan cache ke disk secara atomik."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(CACHE_FILE)


def update_cache(cache: dict, queries: list[ProductQuery], scrape_results: dict) -> int:
    """
    Masukkan hasil batch ke cache. Hanya produk yang berisi kandidat disimpan.
    Mengembalikan jumlah produk baru yang tersimpan.
    """
    added = 0
    for q in queries:
        cands = scrape_results.get(q.index, [])
        priced = [c for c in cands if c.price and c.price > 0]
        if not priced:
            continue  # kosong -> jangan disimpan, biar diretry sesi berikutnya
        cache[query_key(q)] = {
            "candidates": [
                {
                    "marketplace": c.marketplace,
                    "title": c.title,
                    "url": c.url,
                    "price": c.price,
                }
                for c in priced
            ]
        }
        added += 1
    return added


def build_scrape_results(queries: list[ProductQuery], cache: dict) -> dict:
    """
    Bangun scrape_results (index -> list[Candidate]) dari SELURUH cache untuk
    semua produk yang punya data tersimpan. Dipakai analyzer agar Excel selalu
    menampilkan akumulasi semua batch.
    """
    out: dict[int, list[Candidate]] = {}
    for q in queries:
        entry = cache.get(query_key(q))
        if not entry:
            continue
        cands = [
            Candidate(
                marketplace=d["marketplace"],
                title=d["title"],
                url=d["url"],
                price=d["price"],
            )
            for d in entry.get("candidates", [])
            if d.get("price")
        ]
        if cands:
            out[q.index] = cands
    return out
