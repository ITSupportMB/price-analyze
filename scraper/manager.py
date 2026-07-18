"""
Orkestrasi scraping asinkron (Tahap 3).

- Menjalankan seluruh scraper marketplace untuk tiap produk.
- Konkuren dengan batas (semaphore) + jeda acak agar sopan.
- Gagal secara anggun: bila Playwright tidak terpasang / browser tidak ada /
  situs memblokir, produk tetap diproses dengan hasil kosong (No Data).

Hasil: dict {index_produk: [Candidate ter-rank]}.
"""
from __future__ import annotations

import asyncio
import random

from core import config
from core.logger import get_logger

from . import matching
from .base import Candidate, ProductQuery
from .lazada import LazadaScraper
from .shopee import ShopeeScraper
from .tokopedia import TokopediaScraper

log = get_logger()

# Registry marketplace -> kelas scraper.
_REGISTRY = {
    "Tokopedia": TokopediaScraper,
    "Shopee": ShopeeScraper,
    "Lazada": LazadaScraper,
}


def _build_scrapers(names: list[str]):
    scrapers = []
    for n in names:
        cls = _REGISTRY.get(n)
        if cls is None:
            log.warning("Marketplace '%s' tidak dikenal, dilewati.", n)
            continue
        scrapers.append(cls())
    return scrapers


async def _scrape_one(query: ProductQuery, scrapers, context, sem: asyncio.Semaphore) -> list[Candidate]:
    """Cari satu produk di semua marketplace, kembalikan kandidat ter-rank."""
    async with sem:
        all_candidates: list[Candidate] = []
        # Coba hingga (1 + SCRAPE_RETRY) kali bila belum dapat kandidat sama sekali.
        for attempt in range(1 + config.SCRAPE_RETRY):
            all_candidates = []
            for scraper in scrapers:
                try:
                    found = await asyncio.wait_for(
                        scraper.search(query, context), timeout=config.SCRAPE_TIMEOUT
                    )
                    all_candidates.extend(found)
                except asyncio.TimeoutError:
                    log.debug("[%s] timeout untuk '%s'", scraper.name, query.keyword)
                except Exception as exc:  # noqa: BLE001
                    log.debug("[%s] error '%s': %s", scraper.name, query.keyword, exc)
            if all_candidates:
                break
            if attempt < config.SCRAPE_RETRY:
                log.debug("Retry '%s' (percobaan %d kosong)", query.keyword, attempt + 1)
                await asyncio.sleep(random.uniform(1.5, 3.0))
        ranked = matching.rank(query, all_candidates, config.MATCH_THRESHOLD)

        # Verifikasi harga lewat halaman produk resmi (koreksi harga promo-semu
        # dari kartu, mis. Rp15.000 -> Rp55.000). Verifikasi hingga VERIFY_TOP_N
        # kandidat termurah. Bila verifikasi berhasil, pakai harga resmi; bila
        # gagal (URL iklan/timeout), tetap pakai harga kartu (jangan buang match).
        if config.VERIFY_PRICES and ranked:
            by_name = {s.name: s for s in scrapers}
            attempted: set[int] = set()
            for _ in range(config.VERIFY_TOP_N):
                remaining = [
                    c for c in ranked if c.price and c.price > 0 and id(c) not in attempted
                ]
                if not remaining:
                    break
                cheapest = min(remaining, key=lambda c: c.price)
                attempted.add(id(cheapest))
                sc = by_name.get(cheapest.marketplace)
                if sc is None:
                    continue
                try:
                    exact = await asyncio.wait_for(
                        sc.verify_price(cheapest.url, context), timeout=config.SCRAPE_TIMEOUT
                    )
                    if exact and exact > 0:
                        cheapest.price = exact
                        log.debug("Harga terverifikasi '%s': %s", cheapest.title[:40], exact)
                except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                    pass

        # Jeda acak antar produk untuk mengurangi risiko blokir.
        await asyncio.sleep(random.uniform(config.SCRAPE_MIN_DELAY, config.SCRAPE_MAX_DELAY))
        return ranked


def _install_quiet_exception_handler() -> None:
    """
    Redam noise 'Future exception was never retrieved: TargetClosedError' yang
    muncul saat browser ditutup sementara transport internal Playwright masih
    punya future tertunda. Sifatnya kosmetik dan tidak memengaruhi hasil.
    """
    loop = asyncio.get_running_loop()
    default = loop.get_exception_handler()

    def handler(loop, context):
        exc = context.get("exception")
        if exc is not None and type(exc).__name__ == "TargetClosedError":
            return
        (default or loop.default_exception_handler)(context)

    loop.set_exception_handler(handler)


async def _run_async(queries: list[ProductQuery], marketplaces: list[str]) -> dict[int, list[Candidate]]:
    results: dict[int, list[Candidate]] = {q.index: [] for q in queries}
    _install_quiet_exception_handler()

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning(
            "Playwright tidak terpasang -> scraping dilewati (semua produk No Data). "
            "Install: pip install playwright && playwright install chromium"
        )
        return results

    scrapers = _build_scrapers(marketplaces)
    if not scrapers:
        log.warning("Tidak ada scraper aktif -> semua produk No Data.")
        return results

    sem = asyncio.Semaphore(config.SCRAPE_CONCURRENCY)

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=config.SCRAPE_HEADLESS, args=config.BROWSER_ARGS
            )
            context = await browser.new_context(
                user_agent=config.DEFAULT_USER_AGENT,
                locale="id-ID",
                viewport={"width": 1366, "height": 900},
                extra_http_headers={"Accept-Language": "id-ID,id;q=0.9"},
            )
            # Suntik skrip stealth ke setiap halaman (menyamarkan otomasi).
            await context.add_init_script(config.STEALTH_JS)
            if not config.SCRAPE_HEADLESS:
                log.info("Mode browser: headed (jendela Chrome akan muncul).")
            log.info(
                "Searching marketplace... (%d produk x %d marketplace)",
                len(queries),
                len(scrapers),
            )
            tasks = [
                asyncio.create_task(_scrape_one(q, scrapers, context, sem)) for q in queries
            ]

            # Progress bar bila tqdm tersedia.
            try:
                from tqdm.asyncio import tqdm_asyncio

                gathered = await tqdm_asyncio.gather(*tasks, desc="Scraping", unit="produk")
            except Exception:  # noqa: BLE001
                gathered = await asyncio.gather(*tasks)

            for q, cands in zip(queries, gathered):
                results[q.index] = cands

            await context.close()
            await browser.close()
    except Exception as exc:  # noqa: BLE001 - browser gagal launch dsb.
        log.warning("Scraping dibatalkan karena error browser: %s", exc)

    return results


def run_scraping(
    queries: list[ProductQuery], marketplaces: list[str] | None = None
) -> dict[int, list[Candidate]]:
    """Entry point sinkron: jalankan event loop scraping."""
    if not queries:
        return {}
    marketplaces = marketplaces or config.ENABLED_MARKETPLACES
    try:
        return asyncio.run(_run_async(queries, marketplaces))
    except RuntimeError as exc:
        # Mis. dipanggil dari dalam event loop yang sudah berjalan.
        log.error("Tidak bisa menjalankan event loop scraping: %s", exc)
        return {q.index: [] for q in queries}
