"""
Scraper Tokopedia.

Pendekatan: BUKAN mengandalkan nama class CSS (yang ter-hash & sering berubah),
melainkan mengumpulkan semua anchor menuju halaman produk yang mengandung teks
harga "Rp". Cara ini jauh lebih tahan terhadap perubahan markup Tokopedia.

Syarat: berjalan di mode HEADED (SCRAPE_HEADLESS=False). Mode headless diblokir
Tokopedia (ERR_HTTP2_PROTOCOL_ERROR / timeout).
"""
from __future__ import annotations

from core.cleaner import parse_price
from core.logger import get_logger

from .base import Candidate, ProductQuery
from .playwright_base import PlaywrightScraper

log = get_logger()

# Ekstraksi di sisi browser: kembalikan {name, price, href} untuk tiap produk.
# Argumen: maxN = jumlah maksimum hasil.
_JS_EXTRACT = r"""
(maxN) => {
  const out = [], seen = new Set();
  const priceRx = /Rp\s*[\d.]+/;
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.href || '';
    if (!/tokopedia\.com\//.test(href)) continue;
    // Buang tautan non-produk (search, kategori, bantuan, dll.).
    if (/\/(search|find|promo|category|help|about|rules|register|login|discovery)/.test(href)) continue;
    const txt = (a.innerText || '').trim();
    const m = txt.match(priceRx);
    if (!m) continue;                      // hanya anchor yang menampilkan harga
    if (seen.has(href)) continue; seen.add(href);
    // Nama = baris terpanjang yang bukan harga & bukan badge (mis. "63%", "Rp..").
    const lines = txt.split('\n').map(s => s.trim()).filter(Boolean);
    let name = '';
    for (const l of lines) {
      if (l.includes('Rp')) continue;
      if (/^\d+%?$/.test(l)) continue;      // badge diskon / angka polos
      if (l.length > name.length) name = l;
    }
    out.push({ name, price: m[0], href });
    if (out.length >= maxN) break;
  }
  return out;
}
"""


class TokopediaScraper(PlaywrightScraper):
    name = "Tokopedia"
    base_url = "https://www.tokopedia.com"
    search_url_template = "https://www.tokopedia.com/search?st=product&q={q}"
    max_results = 8

    async def search(self, query: ProductQuery, context) -> list[Candidate]:
        url = self.build_search_url(query.keyword)
        page = None
        try:
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=40000)
            await page.wait_for_timeout(5000)
            # Scroll bertahap untuk memicu lazy-load kartu produk.
            for _ in range(4):
                try:
                    await page.mouse.wheel(0, 2200)
                    await page.wait_for_timeout(900)
                except Exception:  # noqa: BLE001
                    break

            raw = await page.evaluate(_JS_EXTRACT, self.max_results)
            results: list[Candidate] = []
            for item in raw:
                name = (item.get("name") or "").strip()
                price = parse_price(item.get("price"))
                if not name or price is None or price <= 0:
                    continue
                results.append(
                    Candidate(
                        marketplace=self.name,
                        title=name,
                        url=item.get("href", ""),
                        price=price,
                        raw={"price_text": item.get("price")},
                    )
                )
            log.debug("[Tokopedia] '%s' -> %d kandidat", query.keyword, len(results))
            return results
        except Exception as exc:  # noqa: BLE001 - anti-bot / timeout / markup berubah
            log.debug("[Tokopedia] gagal mencari '%s': %s", query.keyword, exc)
            return []
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:  # noqa: BLE001
                    pass

    async def verify_price(self, url: str, context) -> float | None:
        """
        Baca harga resmi dari <meta property="product:price:amount"> di halaman
        produk. Jauh lebih akurat daripada harga di kartu pencarian.
        """
        if not url:
            return None
        page = None
        try:
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2500)
            amount = await page.evaluate(
                "() => { const m = document.querySelector("
                "'meta[property=\"product:price:amount\"]'); "
                "return m ? m.getAttribute('content') : null; }"
            )
            price = parse_price(amount) if amount else None
            if price and price > 0:
                log.debug("[Tokopedia] verify %s -> %s", url[:50], price)
                return price
            return None
        except Exception as exc:  # noqa: BLE001
            log.debug("[Tokopedia] verify gagal %s: %s", url[:50], exc)
            return None
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:  # noqa: BLE001
                    pass
