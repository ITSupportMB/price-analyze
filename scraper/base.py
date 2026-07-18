"""
Kontrak dasar untuk semua scraper marketplace.

Setiap scraper menerima ProductQuery dan mengembalikan daftar Candidate.
Scraper WAJIB gagal secara anggun (return []), tidak pernah melempar keluar,
sehingga satu produk/marketplace yang bermasalah tidak menghentikan proses.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from urllib.parse import quote_plus


@dataclass
class ProductQuery:
    """Ringkasan satu produk dari Main Data untuk dicari di marketplace."""

    index: int                       # posisi baris pada master DataFrame
    name: str
    brand: str | None = None
    sku: str | None = None
    barcode: str | None = None
    variant: str | None = None
    main_price: float | None = None
    # Keyword final siap-pakai (sudah dibersihkan dari koma/satuan jual). Bila
    # diisi, dipakai apa adanya untuk pencarian; field lain tetap untuk matching.
    search_override: str | None = None

    @property
    def keyword(self) -> str:
        """
        Keyword pencarian. Prioritas: search_override > barcode > nama (+brand+variant).

        (Barcode dipakai sebagai keyword utama bila tersedia; nama produk tetap
        dipakai untuk penilaian relevansi di tahap matching.)
        """
        if self.search_override:
            return self.search_override
        if self.barcode:
            return self.barcode
        parts = [self.name or ""]
        if self.brand:
            parts.append(self.brand)
        if self.variant:
            parts.append(self.variant)
        return " ".join(p for p in parts if p).strip()


@dataclass
class Candidate:
    """Satu hasil produk dari marketplace."""

    marketplace: str
    title: str
    url: str
    price: float | None
    score: float = 0.0               # diisi oleh matching engine (0-100)
    raw: dict = field(default_factory=dict)


class BaseScraper(abc.ABC):
    """Antarmuka umum scraper marketplace."""

    #: Nama marketplace (mis. "Tokopedia").
    name: str = "Base"
    #: Pola URL pencarian; {q} diganti keyword ter-encode.
    search_url_template: str = ""

    def build_search_url(self, keyword: str) -> str:
        return self.search_url_template.format(q=quote_plus(keyword))

    @abc.abstractmethod
    async def search(self, query: ProductQuery, context) -> list[Candidate]:
        """
        Cari produk di marketplace. `context` adalah Playwright BrowserContext.

        Implementasi harus menangkap semua error internal dan mengembalikan []
        bila gagal / diblokir / tidak ada hasil.
        """
        raise NotImplementedError

    async def verify_price(self, url: str, context) -> float | None:
        """
        Ambil harga RESMI dari halaman produk (lebih akurat daripada kartu
        pencarian yang bisa tercampur cashback/cicilan). Default: tidak
        didukung -> None. Marketplace yang bisa, override method ini.
        """
        return None
