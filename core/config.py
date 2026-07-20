"""
Konfigurasi terpusat untuk Price Analyzer.

Semua "keputusan" yang mungkin berubah (nama folder, pemetaan kolom,
prioritas sumber harga, parameter scraping) dikumpulkan di sini supaya
mudah dikembangkan tanpa menyentuh logika inti.
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Lokasi folder
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "input"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOGS_DIR = PROJECT_ROOT / "logs"

OUTPUT_FILENAME = "Main Data Product.xlsx"

# Ekstensi file produk yang didukung
SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

# ---------------------------------------------------------------------------
# Pemetaan kolom kanonik
# ---------------------------------------------------------------------------
# Struktur file bisa berbeda-beda. Kita memetakan berbagai kemungkinan nama
# kolom (lowercase) ke satu "peran" kanonik yang dipahami analyzer.
# Semua perbandingan dilakukan setelah nama kolom di-lowercase + strip.
COLUMN_ALIASES: dict[str, list[str]] = {
    "product_name": ["name", "nama", "product name", "nama produk", "product", "item name"],
    "brand": ["brand", "merk", "merek", "manufacturer"],
    "sku": ["sku", "kode", "kode produk", "product code", "item code"],
    "barcode": ["barcode", "ean", "upc", "kode barcode"],
    "variant": ["variant_names", "variant", "varian", "variant_label", "size", "ukuran"],
    "category": ["category", "kategori", "classification"],
    "uom": ["uom", "unit", "satuan", "uom_name"],
}

# Kandidat kolom harga jual, diurut berdasarkan prioritas.
# Nilai pertama yang > 0 dipakai sebagai "Harga Main Data".
PRICE_SOURCE_COLUMNS: list[str] = [
    "sell_price",
    "pos_sell_price",
    "uom_sell_price",
    "market_price",
    "buy_price",
    "harga",
    "price",
    "harga jual",
]

# Nama kolom hasil analisa yang ditambahkan ke Main Data (Tahap 4).
ANALYSIS_COLUMNS: list[str] = [
    "Marketplace",
    "Nama Produk Marketplace",
    "Link Produk",
    "Harga Marketplace Termurah",
    "Harga Marketplace Rata-rata",
    "Selisih Harga",
    "Persentase Selisih",
    "Status Harga",
    "Tanggal Cek",
]

# Kolom "harga perusahaan" yang dipakai untuk perbandingan / conditional format.
MAIN_PRICE_COLUMN = "Harga Main Data"

# Kolom meta yang ditambahkan saat merge (Tahap 1).
SOURCE_FILE_COLUMN = "Source File"
IMPORT_DATE_COLUMN = "Import Date"

# Kolom keyword pencarian marketplace setelah dinormalisasi.
SEARCH_KEYWORD_COLUMN = "Search Keyword"

# ---------------------------------------------------------------------------
# Normalisasi keyword pencarian
# ---------------------------------------------------------------------------
# Prefix status stok/pesanan yang dibuang dari keyword pencarian marketplace.
# Hanya dibuang bila berada DI AWAL nama (brand/varian/ukuran/warna/no. seri
# yang kebetulan mengandung kata ini di tengah TIDAK ikut terhapus).
KEYWORD_PREFIXES: list[str] = [
    "PRE ORDER",
    "PRE-ORDER",
    "PO",
    "READY",
    "STOCK",
    "INDENT",
    "PROMO",
    "NEW",
]

# ---------------------------------------------------------------------------
# Status harga
# ---------------------------------------------------------------------------
STATUS_CHEAPER = "Lebih Murah"      # harga kita < marketplace  -> hijau
STATUS_EQUAL = "Sama"               # harga kita = marketplace  -> kuning
STATUS_MORE_EXPENSIVE = "Lebih Mahal"  # harga kita > marketplace -> merah
STATUS_NO_DATA = "No Data"          # tidak ada data marketplace -> tanpa warna

# Warna (ARGB) untuk conditional formatting / summary.
COLOR_GREEN = "FFC6EFCE"
COLOR_GREEN_TEXT = "FF006100"
COLOR_YELLOW = "FFFFEB9C"
COLOR_YELLOW_TEXT = "FF9C6500"
COLOR_RED = "FFFFC7CE"
COLOR_RED_TEXT = "FF9C0006"
COLOR_GREY = "FFD9D9D9"          # produk tanpa data marketplace
COLOR_GREY_TEXT = "FF808080"
COLOR_HEADER = "FF1F4E78"
COLOR_HEADER_TEXT = "FFFFFFFF"

# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------
# Marketplace yang diaktifkan. Bisa dimatikan lewat CLI (--no-scrape).
# Catatan hasil uji lapangan (2026-07):
#   - Tokopedia : BISA di-scrape (mode headed + ekstraksi robust).
#   - Shopee    : diblokir login-wall (butuh akun) -> default OFF.
#   - Lazada    : diblokir captcha -> default OFF.
# Shopee/Lazada masih terdaftar di manager; aktifkan lewat --marketplaces
# bila Anda menyediakan solusi login/captcha sendiri.
ENABLED_MARKETPLACES: list[str] = ["Tokopedia"]

# Jumlah produk yang di-scrape secara paralel.
# PENTING: Tokopedia me-rate-limit bila terlalu banyak tab sekaligus -> hasil
# kosong. Uji lapangan: konkurensi tinggi (5) hit-rate ~3-5/10, sedangkan
# rendah (1-2) ~9/10. Default sengaja rendah demi akurasi. Naikkan hanya bila
# Anda menerima hit-rate lebih rendah demi kecepatan (lihat --concurrency).
SCRAPE_CONCURRENCY = 2
# Ulangi sekali pencarian bila sebuah produk mengembalikan 0 kandidat
# (menangani kegagalan muat transien / cold-start).
SCRAPE_RETRY = 1
# Timeout per pencarian marketplace (detik).
SCRAPE_TIMEOUT = 45
# Ambang skor kecocokan (0-100). Di bawah ini kandidat dianggap tidak relevan.
MATCH_THRESHOLD = 70
# Penyaring outlier murah: kandidat dengan harga < median x nilai ini dibuang
# (mencegah "termurah" tersambar aksesori/sampel/salah satuan). 0.35 = 35%.
PRICE_OUTLIER_FLOOR = 0.35
# Verifikasi harga: buka halaman produk beberapa kandidat termurah untuk baca
# harga RESMI (kartu pencarian kadang salah karena cashback/cicilan). Akurat
# tapi menambah waktu (buka halaman per kandidat). Matikan via --no-verify.
VERIFY_PRICES = True
VERIFY_TOP_N = 3
# Jeda acak antar request supaya lebih sopan / mengurangi blokir (detik).
# Diperbesar demi mengurangi risiko rate-limit pada batch besar.
SCRAPE_MIN_DELAY = 2.0
SCRAPE_MAX_DELAY = 5.0
# User-Agent default untuk request.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Mode browser. Marketplace memblokir mode headless; headed (browser tampil)
# jauh lebih lolos deteksi. Bisa dipaksa headless lewat CLI --headless (berisiko
# diblokir). Sebuah jendela Chrome akan muncul selama proses scraping.
SCRAPE_HEADLESS = False
# Argumen anti-otomasi Chromium.
BROWSER_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
]
# Skrip stealth yang disuntikkan sebelum halaman dimuat (menyamarkan bot).
STEALTH_JS = (
    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id']});"
    "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
    "window.chrome={runtime:{}};"
)


def ensure_dirs() -> None:
    """Pastikan folder wajib tersedia."""
    for d in (INPUT_DIR, OUTPUT_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
