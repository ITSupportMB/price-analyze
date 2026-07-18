"""Scraper Lazada (best-effort)."""
from __future__ import annotations

from .playwright_base import PlaywrightScraper


class LazadaScraper(PlaywrightScraper):
    name = "Lazada"
    base_url = "https://www.lazada.co.id"
    search_url_template = "https://www.lazada.co.id/catalog/?q={q}"

    # Grid Lazada memakai atribut data-qa-locator yang cukup stabil.
    card_selector = "div[data-qa-locator='product-item']"
    title_selector = "div[class*='RfADt'] a, a[title]"
    price_selector = "span[class*='ooOxS'], div[class*='aBrP0'] span"
    link_selector = "a"
    wait_ms = 3000
