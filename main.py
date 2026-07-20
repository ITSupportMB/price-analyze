"""
Price Analyzer - entry point.

Alur (Tahap 1-8):
  1. Baca semua file produk di input/
  2. Cleaning per file
  3. Merge -> Main Data Product
  4. Scraping harga marketplace (Tokopedia/Shopee/Lazada)
  5. Analisa + perhitungan selisih
  6. Tulis Excel: sheet Main Data + Summary, conditional formatting, dll.

Jalankan:
  pip install -r requirements.txt
  playwright install chromium      # opsional, untuk scraping
  python main.py

Opsi:
  python main.py --no-scrape       # lewati scraping (kolom analisa = No Data)
  python main.py --limit 50        # scrape hanya 50 produk pertama (uji cepat)
  python main.py --input <folder>  # folder input lain
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from core import analyzer, cleaner, config, merger, reader
from core.excel_writer import write_report
from core.logger import setup_logger


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Merge produk + analisa harga marketplace.")
    p.add_argument("--input", type=Path, default=config.INPUT_DIR, help="Folder file produk.")
    p.add_argument("--output", type=Path, default=None, help="Path file Excel output.")
    p.add_argument("--no-scrape", action="store_true", help="Lewati scraping marketplace.")
    p.add_argument(
        "--limit", type=int, default=0, help="Batasi jumlah produk yang di-scrape (0 = semua)."
    )
    p.add_argument(
        "--marketplaces",
        type=str,
        default=",".join(config.ENABLED_MARKETPLACES),
        help="Daftar marketplace dipisah koma.",
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="Paksa browser headless (lebih cepat tapi sering diblokir marketplace).",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=0,
        help="Jumlah produk paralel (0 = pakai default config). Rendah (1-2) = "
        "hit-rate lebih tinggi tapi lebih lambat; tinggi = cepat tapi banyak kosong.",
    )
    p.add_argument(
        "--no-verify",
        action="store_true",
        help="Lewati verifikasi harga via halaman produk (lebih cepat, kurang akurat).",
    )
    p.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Mulai scraping dari produk ke-N (untuk batch). Dipadukan dengan --limit.",
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help="Scrape ulang walau sudah ada di cache (mis. untuk update harga).",
    )
    p.add_argument(
        "--next",
        type=int,
        default=0,
        dest="next_n",
        help="Scrape N produk BERIKUTNYA yang belum tercache (otomatis maju tiap "
        "sesi). Cara termudah mencicil ribuan produk; abaikan --offset.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    log = setup_logger()
    config.ensure_dirs()
    started = time.time()

    log.info("=== Price Analyzer mulai ===")

    # --- Tahap 1: baca ---
    frames = reader.read_all(args.input)
    if not frames:
        log.error(
            "Tidak ada file produk yang bisa dibaca di %s. "
            "Letakkan file .xlsx/.csv di folder input lalu jalankan lagi.",
            args.input,
        )
        return 1

    # --- Tahap 2: cleaning ---
    cleaned = cleaner.clean_all(frames)

    # --- Tahap 1: merge ---
    master = merger.merge_frames(cleaned)
    if master.empty:
        log.error("Master data kosong setelah merge. Berhenti.")
        return 1
    log.info("Main Data Product: %d produk, %d kolom.", len(master), master.shape[1])

    # --- Tahap 3-4: scraping (bertahap + cache) ---
    from core import cache

    queries_all = analyzer.build_queries(master)
    cache_data = cache.load_cache()
    log.info("Cache saat ini: %d produk punya data marketplace.", len(cache_data))

    if args.no_scrape:
        log.info("--no-scrape aktif: pakai data cache saja, tanpa scraping.")
    else:
        if args.headless:
            config.SCRAPE_HEADLESS = True
            log.info("--headless aktif (berisiko diblokir marketplace).")
        if args.concurrency and args.concurrency > 0:
            config.SCRAPE_CONCURRENCY = args.concurrency
        if args.no_verify:
            config.VERIFY_PRICES = False
            log.info("--no-verify aktif: harga tidak diverifikasi via halaman produk.")
        log.info("Konkurensi scraping: %d produk paralel.", config.SCRAPE_CONCURRENCY)

        if args.next_n and args.next_n > 0:
            # Mode termudah: ambil N produk berikutnya yang BELUM tercache,
            # otomatis maju tiap sesi tanpa perlu mengatur offset.
            uncached = [q for q in queries_all if cache.query_key(q) not in cache_data]
            to_scrape = uncached[: args.next_n]
            log.info(
                "Mode --next: %d produk belum tercache; ambil %d berikutnya. "
                "Sisa setelah sesi ini: ~%d.",
                len(uncached),
                len(to_scrape),
                max(0, len(uncached) - len(to_scrape)),
            )
        else:
            # Jendela batch manual: produk ke-[offset .. offset+limit).
            offset = max(0, args.offset)
            window = queries_all[offset:]
            if args.limit and args.limit > 0:
                window = window[: args.limit]
            # Lewati yang sudah ada di cache (kecuali --refresh).
            if args.refresh:
                to_scrape = window
            else:
                to_scrape = [q for q in window if cache.query_key(q) not in cache_data]
            log.info(
                "Batch: offset=%d, jendela=%d produk | %d sudah tercache (dilewati), %d akan discrape.",
                offset,
                len(window),
                len(window) - len(to_scrape),
                len(to_scrape),
            )

        if to_scrape:
            # Import lambat supaya --no-scrape tetap jalan tanpa Playwright.
            from scraper.manager import run_scraping

            marketplaces = [m.strip() for m in args.marketplaces.split(",") if m.strip()]
            new_results = run_scraping(to_scrape, marketplaces)
            added = cache.update_cache(cache_data, to_scrape, new_results)
            cache.save_cache(cache_data)
            log.info("Cache diperbarui: +%d produk (total %d).", added, len(cache_data))
        else:
            log.info("Semua produk di jendela ini sudah tercache; tidak ada yang discrape.")

    # scrape_results dibangun dari SELURUH cache -> Excel menampilkan akumulasi
    # semua batch, bukan hanya batch terakhir.
    scrape_results = cache.build_scrape_results(queries_all, cache_data)
    log.info("Total produk dengan data marketplace (akumulasi): %d", len(scrape_results))

    # --- Tahap 5: analisa ---
    analyzed = analyzer.analyze(master, scrape_results)

    # --- Tahap 7: summary ---
    summary = analyzer.build_summary(analyzed)
    log.info("Ringkasan: %s", summary)

    # --- Tahap 6-8: tulis Excel ---
    try:
        out_path = write_report(analyzed, summary, args.output)
    except PermissionError as exc:
        log.error("%s", exc)
        return 1

    elapsed = time.time() - started
    log.info("Done. Output: %s (%.1fs)", out_path, elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
