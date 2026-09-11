"""
scrape_stage1_js.py
===================
Pengganti tahap 1 (panen indeks arsip CNBC) memakai Playwright.

KENAPA HARUS BROWSER OTOMATIS
-----------------------------
Halaman arsip CNBC (cnbc.com/site-map/articles/2024/August/15/) mengembalikan
HTTP 200 dengan HTML ~537 KB, tetapi daftar artikelnya TIDAK ada di dalam HTML
itu. Daftar tersebut digambar oleh JavaScript setelah halaman dimuat.

Dibuktikan lewat pengujian: requests + BeautifulSoup menemukan 0 link artikel;
Playwright pada halaman yang sama menemukan 71 link. Karena itu tahap ini
memakai browser sungguhan yang menjalankan JavaScript, lalu membaca DOM
setelah render selesai.

Tahap 2 dan 3 tidak berubah -- keduanya tetap memakai requests + BeautifulSoup,
karena halaman artikel CNBC sudah berisi metadata lengkap di HTML mentahnya.

DUA OPTIMASI KECEPATAN
----------------------
  1. Blokir gambar, font, CSS, media, dan iklan. Kita hanya butuh teks link;
     mengunduh sisanya membuang ~80% bandwidth dan waktu.
  2. Tunggu SELECTOR link artikel muncul, bukan menunggu waktu tetap.
     Halaman yang sudah siap dalam 1 detik tidak perlu ditunggu 3 detik.

Gabungan keduanya memangkas dari ~7 detik menjadi ~2-3 detik per halaman.

CARA PAKAI
----------
    python scrape_stage1_js.py                    # semua, 1 Sep 2021 - 1 Sep 2026
    python scrape_stage1_js.py --show             # tampilkan jendela browser
    python scrape_stage1_js.py --start 2024-01-01 --end 2024-03-31

Aman dihentikan dengan Ctrl+C. Progres disimpan per bulan; menjalankan ulang
akan melanjutkan dari bulan yang belum selesai.

Prasyarat:
    pip install playwright
    playwright install chromium
"""

import argparse
import json
import re
import time
from datetime import date, timedelta

import pandas as pd
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

import config as C

# Nama bulan ditulis manual, tidak memakai strftime("%B").
# strftime bergantung pada locale sistem -- kalau laptop diset ke bahasa
# Indonesia, hasilnya jadi "Agustus" dan semua URL salah tanpa error apa pun.
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

INDEX_CSV = C.DATA_RAW / "cnbc_index.csv"
CKPT_DIR = C.CHECKPOINT_DIR / "index"
CKPT_DIR.mkdir(parents=True, exist_ok=True)

RE_ART = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/[a-z0-9\-]+\.html")

# Resource yang diblokir. Halaman arsip penuh gambar thumbnail dan skrip iklan
# yang sama sekali tidak kita butuhkan.
BLOCK_TYPES = {"image", "media", "font", "stylesheet"}
BLOCK_URL_HINTS = (
    "doubleclick", "googletagmanager", "google-analytics", "adsystem",
    "chartbeat", "scorecardresearch", "facebook.net", "nr-data.net",
    "krxd.net", "permutive", "taboola", "outbrain",
)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def archive_url(d):
    """https://www.cnbc.com/site-map/articles/2024/August/15/"""
    return f"https://www.cnbc.com/site-map/articles/{d.year}/{MONTHS[d.month-1]}/{d.day}/"


def should_block(route):
    req = route.request
    if req.resource_type in BLOCK_TYPES:
        return route.abort()
    if any(h in req.url for h in BLOCK_URL_HINTS):
        return route.abort()
    return route.continue_()


def scrape_day(page, d):
    """
    Ambil semua link artikel untuk satu tanggal.

    Mengembalikan list of dict. List kosong berarti tidak ada artikel --
    itu wajar untuk hari libur besar, jadi tidak diperlakukan sebagai error.
    """
    url = archive_url(d)
    # Selector yang spesifik ke tanggal halaman ini. Halaman arsip juga memuat
    # link artikel lain di sidebar, jadi menunggu "a" apa pun akan menipu:
    # sidebar muncul duluan, daftar utamanya belum.
    datepath = f"/{d.year}/{d.month:02d}/{d.day:02d}/"
    selector = f"a[href*='{datepath}']"

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except PWTimeout:
        return None  # None = gagal dimuat (beda dari [] = tidak ada artikel)

    try:
        page.wait_for_selector(selector, timeout=12000)
    except PWTimeout:
        # Tidak ada link bertanggal ini setelah 12 detik.
        # Bisa berarti hari itu memang kosong, atau render gagal.
        return []

    pairs = page.eval_on_selector_all(
        selector, "els => els.map(e => [e.href, e.innerText])"
    )

    rows, seen = [], set()
    for href, text in pairs:
        if not href or href in seen:
            continue
        m = RE_ART.search(href)
        if not m:
            continue
        # Verifikasi ulang tanggalnya, jangan percaya selector saja
        if (int(m.group(1)), int(m.group(2)), int(m.group(3))) != (d.year, d.month, d.day):
            continue
        title = (text or "").strip()
        if len(title) < 15:
            continue
        seen.add(href)
        rows.append({"title": title, "url": href, "date": d.isoformat()})

    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=C.START_DATE)
    ap.add_argument("--end", default=C.END_DATE)
    ap.add_argument("--show", action="store_true", help="tampilkan jendela browser")
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    # Kelompokkan tanggal per bulan -> checkpoint jadi 61 file, bukan 1826
    months = {}
    d = start
    while d <= end:
        months.setdefault((d.year, d.month), []).append(d)
        d += timedelta(days=1)

    total_days = (end - start).days + 1
    print(f"Rentang : {start} .. {end}  ({total_days} hari, {len(months)} bulan)")
    print(f"Mode    : {'browser terlihat' if args.show else 'headless'}\n")

    all_rows = []
    done_days = 0
    t0 = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.show)
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        ctx.route("**/*", should_block)
        page = ctx.new_page()

        for i, (ym, days) in enumerate(sorted(months.items()), 1):
            label = f"{ym[0]}-{ym[1]:02d}"
            ckpt = CKPT_DIR / f"{label}.jsonl"

            if ckpt.exists():
                rows = [json.loads(l) for l in ckpt.read_text(encoding="utf-8").splitlines() if l]
                all_rows.extend(rows)
                done_days += len(days)
                print(f"[{i:2}/{len(months)}] {label}  checkpoint  {len(rows):>5} artikel")
                continue

            month_rows = []
            failed = 0
            for day in days:
                rows = scrape_day(page, day)
                if rows is None:
                    failed += 1
                    # Satu kali percobaan ulang. Kegagalan biasanya sesaat.
                    time.sleep(3)
                    rows = scrape_day(page, day) or []
                month_rows.extend(rows)
                done_days += 1

            ckpt.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in month_rows),
                encoding="utf-8",
            )
            all_rows.extend(month_rows)

            # Estimasi sisa waktu, dihitung dari kecepatan sebenarnya
            elapsed = time.time() - t0
            rate = done_days / elapsed if elapsed else 0
            eta = (total_days - done_days) / rate / 60 if rate else 0
            note = f"  ({failed} gagal muat)" if failed else ""
            print(
                f"[{i:2}/{len(months)}] {label}  {len(month_rows):>5} artikel  "
                f"| {rate*60:.0f} hari/menit | sisa ~{eta:.0f} menit{note}"
            )

        browser.close()

    if not all_rows:
        print("\nTidak ada data terkumpul. Periksa instalasi Playwright.")
        return

    df = pd.DataFrame(all_rows).drop_duplicates(subset=["url"]).sort_values("date")
    df.to_csv(INDEX_CSV, index=False)

    n_days_with_data = df["date"].nunique()
    print("\n" + "=" * 58)
    print(f"  Artikel terindeks       : {len(df):,}")
    print(f"  Hari dengan artikel     : {n_days_with_data:,} dari {total_days:,}")
    print(f"  Rata-rata per hari      : {len(df)/max(n_days_with_data,1):.0f}")
    print(f"  Rentang tanggal         : {df['date'].min()} .. {df['date'].max()}")
    print(f"  Waktu total             : {(time.time()-t0)/60:.0f} menit")
    print(f"  Tersimpan               : {INDEX_CSV}")
    print("=" * 58)
    print("\n  Lanjutkan dengan: python scrape_cnbc_html.py --stage2")

    if n_days_with_data < total_days * 0.7:
        print("\n  PERINGATAN: banyak hari tanpa artikel sama sekali.")
        print("  Periksa apakah ada periode panjang yang kosong sebelum lanjut.")


if __name__ == "__main__":
    main()
