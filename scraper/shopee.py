"""Scraper Shopee (best-effort). Shopee sangat agresif memblokir bot."""
from __future__ import annotations

from .playwright_base import PlaywrightScraper


class ShopeeScraper(PlaywrightScraper):
    name = "Shopee"
    base_url = "https://shopee.co.id"
    search_url_template = "https://shopee.co.id/search?keyword={q}"

    # Shopee memakai class ter-hash yang sering berubah + sering memunculkan
    # captcha. Bila diblokir, kartu tidak ditemukan -> [] (No Data).
    card_selector = "div.shopee-search-item-result__item, li.shopee-search-item-result__item"
    title_selector = "div[class*='line-clamp-2'], div.ie3A\\+n"
    price_selector = "span[class*='font-medium'], div[class*='truncate'] , span.ZEgDH9"
    link_selector = "a"
    wait_ms = 3500
