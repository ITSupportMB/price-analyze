"""
Basis scraper berbasis Playwright.

Marketplace nyata (Tokopedia/Shopee/Lazada) memiliki proteksi anti-bot yang
kuat dan struktur HTML yang sering berubah. Kelas ini menyediakan alur
pencarian generik; tiap marketplace cukup mendefinisikan URL + selector.

CATATAN PENTING (jujur soal keterbatasan):
  Selector di bawah bersifat best-effort dan mudah usang. Bila situs memblokir
  bot atau mengubah markup, scraper akan mengembalikan [] (bukan error), dan
  produk ditandai "No Data". Perbarui selector saat diperlukan.
"""
from __future__ import annotations

import asyncio

from core.cleaner import parse_price
from core.logger import get_logger

from .base import BaseScraper, Candidate, ProductQuery

log = get_logger()


class PlaywrightScraper(BaseScraper):
    """Scraper generik: buka halaman pencarian, ekstrak kartu produk."""

    # --- Selector yang di-override tiap marketplace ---
    card_selector: str = ""      # elemen pembungkus tiap produk
    title_selector: str = ""     # judul produk di dalam kartu
    price_selector: str = ""     # harga di dalam kartu
    link_selector: str = "a"     # tautan produk di dalam kartu

    max_results: int = 8         # ambil beberapa teratas saja
    wait_ms: int = 2500          # jeda muat konten dinamis

    async def _inner_text(self, node, selector: str) -> str | None:
        try:
            el = await node.query_selector(selector)
            if el is None:
                return None
            txt = await el.inner_text()
            return txt.strip() if txt else None
        except Exception:  # noqa: BLE001
            return None

    async def _href(self, node, selector: str) -> str | None:
        try:
            el = await node.query_selector(selector)
            if el is None:
                return None
            href = await el.get_attribute("href")
            return href
        except Exception:  # noqa: BLE001
            return None

    async def search(self, query: ProductQuery, context) -> list[Candidate]:
        url = self.build_search_url(query.keyword)
        page = None
        try:
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=self.wait_ms * 6)
            # Beri waktu konten dinamis termuat + sedikit scroll agar lazy-load jalan.
            await page.wait_for_timeout(self.wait_ms)
            try:
                await page.mouse.wheel(0, 2000)
                await page.wait_for_timeout(1000)
            except Exception:  # noqa: BLE001
                pass

            cards = await page.query_selector_all(self.card_selector)
            if not cards:
                log.debug("[%s] Tidak ada kartu produk untuk '%s'", self.name, query.keyword)
                return []

            results: list[Candidate] = []
            for card in cards[: self.max_results]:
                title = await self._inner_text(card, self.title_selector)
                price_txt = await self._inner_text(card, self.price_selector)
                href = await self._href(card, self.link_selector)
                if not title:
                    continue
                results.append(
                    Candidate(
                        marketplace=self.name,
                        title=title,
                        url=self._absolutize(href),
                        price=parse_price(price_txt),
                        raw={"price_text": price_txt},
                    )
                )
            log.debug("[%s] '%s' -> %d kandidat", self.name, query.keyword, len(results))
            return results
        except Exception as exc:  # noqa: BLE001 - anti-bot/timeout/markup berubah
            log.debug("[%s] gagal mencari '%s': %s", self.name, query.keyword, exc)
            return []
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:  # noqa: BLE001
                    pass

    base_url: str = ""

    def _absolutize(self, href: str | None) -> str:
        if not href:
            return ""
        if href.startswith("http"):
            return href
        if href.startswith("//"):
            return "https:" + href
        return self.base_url.rstrip("/") + "/" + href.lstrip("/")
