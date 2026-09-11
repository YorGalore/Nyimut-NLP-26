"""
test_archive.py
===============
Skrip sekali pakai. Menjawab dua pertanyaan:

  1. Apakah format nama-bulan-kapital (2024/August/15/) benar-benar
     menampilkan daftar artikel?
  2. Apakah arsip terisi untuk tanggal LAMA (2021) atau hanya yang baru?

Pertanyaan kedua menentukan nasib proyek: kalau arsip hanya terisi beberapa
bulan terakhir, kita tidak bisa dapat 5 tahun dari sini dan harus pindah sumber.

Jalankan:  python test_archive.py
"""

import re
import time

from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as _http
    _IMP = {"impersonate": "chrome124"}
except ImportError:
    import requests as _http
    _IMP = {}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

S = _http.Session()
S.headers.update(HEADERS)

RE_ART = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/[a-z0-9\-]+\.html")

# Tanggal uji: sengaja hari kerja biasa (bukan libur, bukan akhir pekan),
# tersebar dari awal sampai akhir rentang tugas.
TESTS = [
    (2021, "September", 15),
    (2022, "June", 15),
    (2023, "March", 15),
    (2024, "August", 15),
    (2025, "May", 15),
    (2026, "August", 12),
]


def check(year, month, day):
    url = f"https://www.cnbc.com/site-map/articles/{year}/{month}/{day}/"
    try:
        r = S.get(url, timeout=25, **_IMP)
    except Exception as exc:
        return url, f"ERROR {type(exc).__name__}", 0, None

    if r.status_code != 200:
        return url, f"HTTP {r.status_code}", 0, None

    html = r.text
    soup = BeautifulSoup(html, "html.parser")

    # Tanda paling jelas kalau arsip kosong
    empty = "No articles for this day" in html

    # Hitung link artikel yang TANGGALNYA COCOK dengan halaman yang diminta.
    # Ini penting: halaman CNBC selalu punya link artikel lain di sidebar,
    # jadi menghitung semua link akan menipu kita.
    matched = set()
    for a in soup.find_all("a", href=True):
        m = RE_ART.search(a["href"])
        if m and int(m.group(1)) == year and int(m.group(3)) == day:
            matched.add(a["href"])

    sample = None
    for a in soup.find_all("a", href=True):
        m = RE_ART.search(a["href"])
        if m and int(m.group(1)) == year and int(m.group(3)) == day:
            title = a.get_text(strip=True)
            if len(title) > 15:
                sample = title[:70]
                break

    status = "KOSONG (No articles for this day)" if empty else "ada isi"
    return url, status, len(matched), sample


print("Menguji format nama-bulan-kapital pada 6 tanggal\n")
print(f"{'TANGGAL':<22} {'STATUS':<34} {'LINK':>5}")
print("-" * 66)

results = []
for year, month, day in TESTS:
    url, status, n, sample = check(year, month, day)
    label = f"{year}/{month}/{day}"
    print(f"{label:<22} {status:<34} {n:>5}")
    if sample:
        print(f"  contoh: {sample}")
    results.append((label, n))
    time.sleep(2)

print("-" * 66)

ok = [r for r in results if r[1] > 0]
print(f"\nTanggal dengan artikel: {len(ok)} dari {len(results)}")

if len(ok) == len(results):
    print("\nSEMUA TERISI -> rute sitemap HIDUP. Lanjut stage 1.")
elif len(ok) == 0:
    print("\nSEMUA KOSONG -> arsip CNBC tidak terpakai. Pindah sumber berita.")
else:
    print("\nSEBAGIAN TERISI -> arsip hanya mencakup periode tertentu.")
    print("Periode yang tersedia:", ", ".join(l for l, n in ok))
    print("Kalau tidak mencakup 5 tahun penuh, pindah sumber.")