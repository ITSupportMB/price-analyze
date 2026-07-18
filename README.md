# Price Analyzer

Aplikasi Python untuk **menggabungkan seluruh file produk** dalam satu folder
menjadi satu file master (`Main Data Product.xlsx`), lalu **membandingkan harga**
produk terhadap marketplace (Tokopedia, Shopee, Lazada) dan menghasilkan
**laporan Excel profesional** dengan pewarnaan otomatis.

---

## Fitur

| Tahap | Fungsi |
|------|--------|
| 1 | Baca & gabung semua file `.xlsx` / `.csv` dari `input/` (union kolom by-name) |
| 2 | Cleaning: hapus baris kosong & duplikat, rapikan teks, harga -> numerik, SKU seragam, encoding aman |
| 3 | Normalisasi keyword + scraping harga marketplace (async, Playwright) + pencocokan relevansi (rapidfuzz) |
| 4 | Tambah kolom analisa (Search Keyword, Marketplace, Link, Termurah, Rata-rata, Selisih, %, Status, Tanggal) |
| 5 | Perhitungan selisih & persentase |
| 6 | Highlight seluruh baris (hijau/kuning/merah/abu-abu) + Conditional Formatting |
| 7 | Sheet `Summary` (statistik ringkas) |
| 8 | Auto Filter, Freeze Pane, Auto Fit lebar kolom, format Rupiah |

---

## Struktur Project

```
price-analyzer/
├── input/                # letakkan file produk di sini (.xlsx / .csv)
├── output/               # Main Data Product.xlsx dihasilkan di sini
├── logs/                 # log tiap proses (run_YYYYMMDD_HHMMSS.log)
├── core/
│   ├── config.py         # semua konfigurasi (kolom, harga, warna, scraping)
│   ├── logger.py         # logging console + file
│   ├── reader.py         # Tahap 1: baca file (encoding-safe)
│   ├── cleaner.py        # Tahap 2: cleaning
│   ├── merger.py         # Tahap 1: gabung + Harga Main Data
│   ├── analyzer.py       # Tahap 4-5,7: analisa + summary
│   └── excel_writer.py   # Tahap 6-8: tulis Excel + formatting
├── scraper/
│   ├── base.py           # kontrak ProductQuery / Candidate / BaseScraper
│   ├── playwright_base.py# basis scraper Playwright
│   ├── tokopedia.py      # scraper Tokopedia
│   ├── shopee.py         # scraper Shopee
│   ├── lazada.py         # scraper Lazada
│   ├── matching.py       # skor relevansi (SKU>barcode>nama>merk>ukuran)
│   └── manager.py        # orkestrasi async + fallback anggun
├── main.py               # entry point
├── requirements.txt
└── README.md
```

---

## Cara Menjalankan

```bash
# 1. Install dependency
pip install -r requirements.txt

# 2. (Opsional) install browser untuk scraping live
playwright install chromium

# 3. Letakkan file produk di folder input/
#    contoh: input/Product A.xlsx, input/Product B.csv

# 4. Jalankan
python main.py

# Jika langkah 1 dan 2 tidak bisa check dulu apakah python sudah di install dengan 
python --version 

# atau 

py --version

# jiak versi nya muncul maka bisa tambbahkan command nya jadi seperti ini
python -m pip install -r requirements.txt

# untuk yang langkah kedua juga sama
python -m playwright install chromium

```

Hasil: `output/Main Data Product.xlsx` (sheet **Main Data** + **Summary**).

### Opsi CLI

```bash
python main.py --no-scrape           # hanya merge + cleaning + Excel (tanpa scraping)
python main.py --limit 50            # scrape 50 produk pertama (uji cepat)
python main.py --input "D:/data"     # folder input lain
python main.py --marketplaces Tokopedia          # default (Shopee/Lazada diblokir)
python main.py --headless            # paksa headless (lebih cepat, sering diblokir)
```

> Saat scraping, **jendela Chrome akan muncul** (mode headed) dan **jangan
> ditutup** sampai proses selesai. Pastikan file output tidak sedang dibuka
> di Excel (kalau terkunci, program memberi pesan jelas & berhenti aman).

---

## Cara Kerja Analisa Harga

- **Normalisasi keyword** (sebelum pencarian): hapus teks dalam `[]` dan prefix
  status di awal nama — `PO`, `PRE ORDER`, `PRE-ORDER`, `READY`, `STOCK`,
  `INDENT`, `PROMO`, `NEW`. Brand, variant, ukuran, volume, warna, dan nomor
  seri **tidak** dihapus.

  | Nama asli | Search Keyword |
  |---|---|
  | `[PO] Sika Grout 214-11 25Kg` | `Sika Grout 214-11 25Kg` |
  | `[READY] Cat Avian 5Kg` | `Cat Avian 5Kg` |
  | `[INDENT] Semen Tiga Roda` | `Semen Tiga Roda` |

  Hasilnya disimpan di kolom **`Search Keyword`** (tepat setelah nama produk).
  Kolom nama asli tetap utuh. Prefix hanya dibuang bila di **awal**, sehingga
  `Poles`, `Promosa`, `Newton`, `Stockholm`, dan `Cat Avian NEW 5Kg` aman.

  Keyword juga dibuang **koma** dan **satuan jual** (`Per Pcs`, `Per Zak`,
  `Per Pail`, dst.) agar pencarian tidak terlalu spesifik. Contoh:
  `Sika Sikaflex 211 Sosis - Hitam,600 ML,Per Pcs` → `Sika Sikaflex 211 Sosis Hitam 600 ML`.
  Uji nyata: pembersihan ini menaikkan hit-rate Tokopedia dari ~2/10 → ~5/10.
- **Keyword pencarian**: barcode > nama ternormalisasi (+ merk + varian).
- **Pemilihan hasil** (paling relevan): SKU → barcode → nama → merk → ukuran/volume.
- **Guard spesifikasi**: produk dengan ukuran berbeda **tidak** dibandingkan.
- **Acuan perbandingan**: harga marketplace **termurah** (benchmark paling ketat).

```
Selisih    = Harga Marketplace Termurah - Harga Main Data
Persentase = Selisih / Harga Marketplace Termurah × 100%
```

| Kondisi | Status | Warna |
|---|---|---|
| Harga kita < marketplace | Lebih Murah | 🟢 Hijau |
| Harga kita = marketplace | Sama | 🟡 Kuning |
| Harga kita > marketplace | Lebih Mahal | 🔴 Merah |
| Tidak ditemukan / harga kosong | No Data | ⚪ Abu-abu |

Warna diterapkan pada **seluruh baris** memakai `PatternFill` openpyxl, jadi
benar-benar tersimpan di dalam file `.xlsx` (bukan sekadar aturan formatting).
Sebagai pelengkap, Conditional Formatting tetap aktif pada kolom
`Harga Main Data` agar warna ikut menyesuaikan bila harga diedit manual.

---

## Catatan Penting soal Scraping (jujur — hasil uji lapangan)

Diuji langsung (Juli 2026):

| Marketplace | Status | Keterangan |
|---|---|---|
| 🟢 **Tokopedia** | **Berfungsi** | Wajib mode **headed** (browser tampil) + ekstraksi berbasis href/regex "Rp" (tidak bergantung nama class). Data harga nyata masuk. |
| 🔴 **Shopee** | Diblokir | Login-wall — hasil pencarian tidak muncul untuk pengunjung anonim. |
| 🔴 **Lazada** | Diblokir | Captcha challenge. |

Karena itu **default `ENABLED_MARKETPLACES = ["Tokopedia"]`**. Shopee & Lazada
tetap tersedia di kode (aktifkan via `--marketplaces Tokopedia,Shopee,Lazada`),
tapi realistis akan mengembalikan `No Data` tanpa solusi login/captcha.

Hal yang perlu diketahui saat scraping:

- **Sebuah jendela Chrome akan terbuka** selama proses (mode headed). Jangan
  ditutup. Mode headless (`--headless`) lebih cepat tapi **diblokir** Tokopedia.
- **Konkurensi vs akurasi**: Tokopedia me-rate-limit bila banyak tab sekaligus.
  Uji lapangan: konkurensi 5 → hit-rate ~3-5/10; konkurensi **1-2 → ~9-10/10**.
  Default `SCRAPE_CONCURRENCY=2` + retry sekali untuk produk yang kosong.
  Atur dengan `--concurrency N` (rendah = akurat tapi lambat).
- **Penyaring outlier**: harga kandidat yang tak wajar murah (< 35% median,
  mis. aksesori/sampel/salah satuan) dibuang agar "termurah" tidak menyesatkan.
- **Waktu**: konkurensi rendah lebih akurat tapi lebih lambat (~20-30 detik/
  produk). Untuk ribuan produk butuh berjam-jam — jalankan bertahap dengan
  `--limit N`, atau semalaman.
- **Match rate wajar tidak 100%**: produk yang tak ada di marketplace, nama
  terlalu generik, atau ukuran beda akan `No Data` (by design, Tahap 12).
- Bila situs memblokir / markup berubah, produk otomatis `No Data` dan proses
  **tetap lanjut**. Selector/ekstraksi ada di `scraper/tokopedia.py`.
- Pipeline **merge + cleaning + Excel report berjalan 100%** tanpa scraping.
  Gunakan `--no-scrape` untuk laporan tanpa menyentuh marketplace.

Untuk produksi yang butuh data harga andal & skala besar, **API resmi**
marketplace atau layanan data pihak ketiga jauh lebih stabil daripada scraping.

---

## Konfigurasi

Semua parameter ada di `core/config.py`:

- `COLUMN_ALIASES` — pemetaan nama kolom (tambah alias bila file Anda berbeda).
- `PRICE_SOURCE_COLUMNS` — prioritas kolom harga jual.
- `ENABLED_MARKETPLACES`, `SCRAPE_CONCURRENCY`, `MATCH_THRESHOLD`, dll.
```
