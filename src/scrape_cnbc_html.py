"""
scrape_cnbc_html.py
===================
Scraping berita CNBC dengan parsing HTML murni (requests + BeautifulSoup).
Tidak memakai API apa pun.

STRATEGI: SITEMAP ARSIP HARIAN
------------------------------
Halaman section CNBC (cnbc.com/world-economy) memuat kontennya lewat infinite
scroll JavaScript, jadi requests hanya mendapat shell kosong. Tapi CNBC juga
menyediakan halaman arsip per tanggal yang berisi daftar link artikel hari itu
sebagai HTML statis biasa:

    https://www.cnbc.com/site-map/articles/2024/January/15/

Halaman itulah pintu masuk kita.

TIGA TAHAP
----------
  Tahap 1  panen indeks    : 1.826 halaman arsip -> judul + URL (~300.000 baris)
  Tahap 2  filter judul    : leksikon dijalankan SEBELUM fetch artikel,
                             supaya tahap 3 hanya memproses yang relevan
  Tahap 3  panen artikel   : fetch tiap artikel terpilih -> timestamp presisi,
                             isi artikel penuh, author, section

Tahap 2 diletakkan di tengah bukan di akhir karena itu satu-satunya cara
membuat tahap 3 selesai dalam hitungan jam, bukan hari. Memfilter 300.000
judul itu gratis; men-download 300.000 halaman tidak.

CARA PAKAI
----------
    python scrape_cnbc_html.py --probe       # cari pola URL yang benar
    python scrape_cnbc_html.py --stage1      # panen indeks (jalankan semalaman)
    python scrape_cnbc_html.py --stage2      # filter judul
    python scrage_cnbc_html.py --stage3      # panen artikel
    python scrape_cnbc_html.py --stage3 --limit-articles 3000   # kalau mepet waktu

Setiap tahap bisa dihentikan (Ctrl+C) dan dilanjutkan. Progres disimpan.

SOAL BOT DETECTION
------------------
CNBC memakai Akamai. Mitigasi berlapis di skrip ini:
  - requests.Session persisten supaya cookie tersimpan antar request
  - header browser lengkap (bukan hanya User-Agent)
  - jeda acak, bukan jeda tetap
  - backoff eksponensial saat kena 403/429
  - kalau paket curl_cffi terpasang, otomatis dipakai untuk meniru TLS
    fingerprint Chrome asli (paling ampuh melawan Akamai):
        pip install curl_cffi
"""

import argparse
import json
import random
import re
import sys
import time
from datetime import date, timedelta

import pandas as pd
from bs4 import BeautifulSoup

import config as C

# ---------------------------------------------------------------------------
# LAPISAN HTTP
# ---------------------------------------------------------------------------
# curl_cffi meniru TLS/JA3 fingerprint Chrome. Akamai memeriksa ini, dan
# requests biasa punya fingerprint yang jelas-jelas bukan browser.
# Kalau paketnya tidak ada, fallback ke requests biasa (sering tetap jalan).
try:
    from curl_cffi import requests as _http
    _IMPERSONATE = {"impersonate": "chrome124"}
    print("[info] memakai curl_cffi (TLS fingerprint Chrome)")
except ImportError:
    import requests as _http
    _IMPERSONATE = {}
    print("[info] curl_cffi tidak ada, memakai requests biasa")
    print("[info] kalau banyak kena 403, jalankan: pip install curl_cffi")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}

SESSION = _http.Session()
SESSION.headers.update(BROWSER_HEADERS)


def get_html(url, max_retry=3):
    """
    Ambil HTML satu halaman, dengan retry dan backoff.

    Mengembalikan string HTML, atau None kalau gagal permanen.
    404 langsung dianggap gagal tanpa retry -- halaman arsip untuk tanggal
    tertentu memang bisa saja tidak ada, dan mencoba ulang hanya buang waktu.
    """
    for attempt in range(1, max_retry + 1):
        try:
            resp = SESSION.get(url, timeout=25, **_IMPERSONATE)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 404:
                return None
            if resp.status_code in (403, 429):
                wait = 5 * (2 ** attempt)   # blokir butuh jeda lebih panjang
                print(f"    [{resp.status_code}] diblokir, tunggu {wait}s")
                time.sleep(wait)
                continue
            print(f"    [{resp.status_code}] {url}")
        except Exception as exc:
            print(f"    [retry {attempt}] {type(exc).__name__}: {exc}")
            time.sleep(2 ** attempt)
    return None


def polite_sleep(fast=False):
    """
    Jeda acak, bukan tetap. Interval yang terlalu teratur adalah pola yang
    justru dikenali sebagai bot.
    """
    time.sleep(random.uniform(0.4, 0.9) if fast else random.uniform(1.0, 2.0))


# ---------------------------------------------------------------------------
# POLA URL ARSIP
# ---------------------------------------------------------------------------
# Format persisnya belum diverifikasi. --probe akan mencoba semuanya dan
# melaporkan mana yang hidup. Setelah ketahuan, isi ARCHIVE_PATTERN di bawah.
URL_PATTERNS = {
    "month_name_cap": lambda d: f"https://www.cnbc.com/site-map/articles/{d.year}/{d.strftime('%B')}/{d.day}/",
    "month_name_low": lambda d: f"https://www.cnbc.com/site-map/articles/{d.year}/{d.strftime('%B').lower()}/{d.day}/",
    "month_num":      lambda d: f"https://www.cnbc.com/site-map/articles/{d.year}/{d.month}/{d.day}/",
    "month_num_pad":  lambda d: f"https://www.cnbc.com/site-map/articles/{d.year}/{d.month:02d}/{d.day:02d}/",
    "no_trailing":    lambda d: f"https://www.cnbc.com/site-map/articles/{d.year}/{d.strftime('%B')}/{d.day}",
}

# Isi setelah --probe memberi tahu mana yang benar.
ARCHIVE_PATTERN = "month_name_cap"

INDEX_CSV = C.DATA_RAW / "cnbc_index.csv"          # tahap 1
SHORTLIST_CSV = C.DATA_RAW / "cnbc_shortlist.csv"  # tahap 2
INDEX_CKPT = C.CHECKPOINT_DIR / "index"
ARTICLE_CKPT = C.CHECKPOINT_DIR / "articles"
INDEX_CKPT.mkdir(parents=True, exist_ok=True)
ARTICLE_CKPT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# PROBE
# ---------------------------------------------------------------------------
def run_probe():
    """
    Coba kelima pola URL pada satu tanggal, laporkan mana yang berhasil,
    dan simpan HTML mentahnya supaya struktur tag bisa diperiksa manual.
    """
    test_day = date(2024, 1, 15)
    print(f"Menguji pola URL arsip untuk tanggal {test_day}\n")

    winner = None
    for name, fn in URL_PATTERNS.items():
        url = fn(test_day)
        print(f"  {name:16s} {url}")
        html = get_html(url, max_retry=1)
        if html and len(html) > 5000:
            links = BeautifulSoup(html, "html.parser").select("a[href*='/2024/01/']")
            print(f"    -> OK ({len(html):,} byte, {len(links)} link artikel terdeteksi)")
            if winner is None and links:
                winner = (name, url, html)
        else:
            print("    -> gagal / kosong")
        time.sleep(2)

    if not winner:
        print("\nSemua pola gagal. Kemungkinan:")
        print("  1. Diblokir bot detection  -> pip install curl_cffi, ulangi")
        print("  2. Struktur URL berubah    -> buka cnbc.com/site-map/ di browser,")
        print("     klik sampai halaman per-tanggal, salin URL-nya ke URL_PATTERNS")
        sys.exit(1)

    name, url, html = winner
    out = C.DATA_RAW / "_probe_archive.html"
    out.write_text(html, encoding="utf-8")

    print(f"\nPola yang berhasil: '{name}'")
    print(f">> Set ARCHIVE_PATTERN = \"{name}\" di bagian atas file ini.")
    print(f">> HTML mentah disimpan di {out} -- buka dan periksa struktur tag-nya.")

    soup = BeautifulSoup(html, "html.parser")
    links = [a for a in soup.find_all("a", href=True) if re.search(r"/\d{4}/\d{2}/\d{2}/", a["href"])]
    print(f"\nContoh 5 link artikel yang terparse:")
    for a in links[:5]:
        print(f"  {a.get_text(strip=True)[:70]}")
        print(f"    {a['href']}")


# ---------------------------------------------------------------------------
# TAHAP 1 -- PANEN INDEKS
# ---------------------------------------------------------------------------
RE_ARTICLE_URL = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")


def parse_archive_page(html, day):
    """
    Parse satu halaman arsip harian -> daftar {title, url, date}.

    Kita tidak bergantung pada nama class CSS di sini, melainkan pada POLA URL
    artikel CNBC (/YYYY/MM/DD/slug.html). Nama class berubah tiap redesign;
    struktur URL jauh lebih stabil. Ini keputusan desain yang disengaja.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows, seen = [], set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not RE_ARTICLE_URL.search(href):
            continue
        if href.startswith("/"):
            href = "https://www.cnbc.com" + href
        if "cnbc.com" not in href or href in seen:
            continue

        title = a.get_text(strip=True)
        if len(title) < 15:      # link navigasi / gambar tanpa teks
            continue

        seen.add(href)
        rows.append({"title": title, "url": href, "date": day.isoformat()})

    return rows


def run_stage1():
    """
    Loop semua tanggal dalam rentang tugas.

    Checkpoint per BULAN, bukan per hari: 60 file, bukan 1.826.
    Bulan yang sudah punya checkpoint otomatis dilewati, jadi skrip aman
    dihentikan Ctrl+C dan dijalankan ulang.
    """
    fn = URL_PATTERNS[ARCHIVE_PATTERN]
    start = date.fromisoformat(C.START_DATE)
    end = date.fromisoformat(C.END_DATE)

    # kelompokkan tanggal per bulan
    months = {}
    d = start
    while d <= end:
        months.setdefault((d.year, d.month), []).append(d)
        d += timedelta(days=1)

    print(f"{len(months)} bulan, {(end-start).days + 1} hari total\n")
    all_rows = []

    for i, (ym, days) in enumerate(sorted(months.items()), 1):
        ckpt = INDEX_CKPT / f"{ym[0]}-{ym[1]:02d}.jsonl"

        if ckpt.exists():
            rows = [json.loads(l) for l in ckpt.read_text(encoding="utf-8").splitlines() if l]
            all_rows.extend(rows)
            print(f"[{i}/{len(months)}] {ym[0]}-{ym[1]:02d} -- checkpoint ({len(rows)} artikel)")
            continue

        month_rows = []
        for day in days:
            html = get_html(fn(day))
            if html:
                found = parse_archive_page(html, day)
                month_rows.extend(found)
            polite_sleep(fast=True)

        with ckpt.open("w", encoding="utf-8") as f:
            for r in month_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        all_rows.extend(month_rows)
        print(f"[{i}/{len(months)}] {ym[0]}-{ym[1]:02d} -- {len(month_rows)} artikel")

    df = pd.DataFrame(all_rows).drop_duplicates(subset=["url"])
    df.to_csv(INDEX_CSV, index=False)

    print("\n" + "=" * 55)
    print(f"  Total artikel terindeks : {len(df):,}")
    print(f"  Rentang tanggal         : {df['date'].min()} .. {df['date'].max()}")
    print(f"  Rata-rata per hari      : {len(df) / max(len(df['date'].unique()), 1):.0f}")
    print(f"  Tersimpan               : {INDEX_CSV}")
    print("=" * 55)

    if len(df) < 10_000:
        print("\n  PERINGATAN: hasil jauh lebih sedikit dari perkiraan (~300rb).")
        print("  Kemungkinan parse_archive_page() tidak menangkap struktur link.")
        print("  Periksa data/raw/_probe_archive.html secara manual.")


# ---------------------------------------------------------------------------
# TAHAP 2 -- FILTER DI LEVEL JUDUL
# ---------------------------------------------------------------------------
def run_stage2():
    """
    Skor semua judul dengan leksikon dari config.py, ambil yang lolos ambang.

    Ini filter berbasis JUDUL saja -- sengaja lebih longgar dari filter final
    di preprocess_news.py, karena judul lebih pendek dan lebih mudah
    melewatkan artikel relevan. Presisi diserahkan ke tahap berikutnya;
    di sini yang penting recall.
    """
    df = pd.read_csv(INDEX_CSV)
    print(f"Menyaring {len(df):,} judul...")

    patterns = {
        t: re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE)
        for t in C.GEO_LEXICON
    }
    neg = [re.compile(re.escape(t), re.IGNORECASE) for t in C.NEGATIVE_LEXICON]

    def score(title):
        title = str(title)
        s, matched = 0, []
        for term, weight in C.GEO_LEXICON.items():
            if patterns[term].search(title):
                s += weight
                matched.append(term)
        return s, "|".join(matched)

    scored = df["title"].apply(score)
    df["title_score"] = [s for s, _ in scored]
    df["matched_terms"] = [m for _, m in scored]
    df["has_negative"] = df["title"].astype(str).apply(
        lambda t: any(p.search(t) for p in neg)
    )

    # Ambang 1 (bukan 2 seperti filter final): judul jauh lebih pendek dari
    # judul+deskripsi, jadi ambang yang sama akan membuang terlalu banyak.
    keep = (df["title_score"] >= 1) & (~df["has_negative"])
    out = df[keep].sort_values("date")
    out.to_csv(SHORTLIST_CSV, index=False)

    print(f"\n  Lolos filter : {len(out):,} ({len(out)/len(df)*100:.1f}%)")
    print(f"  Estimasi waktu tahap 3 : {len(out) * 1.2 / 3600:.1f} jam")
    print(f"  Tersimpan    : {SHORTLIST_CSV}")
    print("\n  Distribusi skor judul:")
    print(out["title_score"].value_counts().sort_index().to_string())
    print("\n  Contoh 5 judul yang lolos:")
    for t in out["title"].head(5):
        print(f"    - {t[:85]}")


# ---------------------------------------------------------------------------
# TAHAP 3 -- PANEN ARTIKEL
# ---------------------------------------------------------------------------
# Selector ditulis sebagai daftar kandidat berurutan, bukan satu tebakan mati.
# Nama class CNBC berubah tiap redesign; artikel lama dan baru bisa memakai
# struktur berbeda. Kandidat pertama yang cocok dipakai.
BODY_SELECTORS = [
    "div.ArticleBody-articleBody",
    "div[data-module='ArticleBody']",
    "div.group",
    "article",
]


def parse_article(html, url):
    """
    Ekstrak satu artikel.

    Strategi utama: JSON-LD. CNBC menyematkan <script type="application/ld+json">
    berisi metadata terstruktur (headline, datePublished, author, articleBody).
    Ini jauh lebih stabil daripada mengejar nama class CSS, dan memberi
    timestamp presisi detik yang kita butuhkan untuk aturan cutoff 08:00 WIB.

    Kalau JSON-LD tidak ada, jatuh ke meta tag, lalu ke selector CSS.
    """
    soup = BeautifulSoup(html, "html.parser")
    rec = {"url": url}

    # -- lapis 1: JSON-LD --
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            data = next((d for d in data if isinstance(d, dict)), {})
        if not isinstance(data, dict):
            continue
        if data.get("@type") in ("NewsArticle", "Article", "ReportageNewsArticle"):
            rec["title"] = data.get("headline")
            rec["published"] = data.get("datePublished")
            rec["modified"] = data.get("dateModified")
            rec["description"] = data.get("description")
            rec["body"] = data.get("articleBody")
            author = data.get("author")
            if isinstance(author, dict):
                rec["author"] = author.get("name")
            elif isinstance(author, list):
                rec["author"] = ", ".join(
                    a.get("name", "") for a in author if isinstance(a, dict)
                )
            break

    # -- lapis 2: meta tag --
    def meta(prop):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return tag.get("content") if tag else None

    rec.setdefault("title", None)
    rec["title"] = rec.get("title") or meta("og:title")
    rec["description"] = rec.get("description") or meta("og:description")
    rec["published"] = rec.get("published") or meta("article:published_time")
    rec["section"] = meta("article:section") or meta("og:section")

    # -- lapis 3: selector CSS untuk isi artikel --
    if not rec.get("body"):
        for sel in BODY_SELECTORS:
            node = soup.select_one(sel)
            if node:
                paras = [p.get_text(" ", strip=True) for p in node.find_all("p")]
                if len(paras) >= 3:
                    rec["body"] = " ".join(paras)
                    break

    return rec


def run_stage3(limit=None):
    """
    Fetch tiap artikel di shortlist.

    Checkpoint per 200 artikel, dan artikel yang sudah pernah diambil
    dilewati. Dengan begitu skrip bisa dihentikan kapan saja tanpa kehilangan
    progres -- penting karena tahap ini yang paling lama.
    """
    df = pd.read_csv(SHORTLIST_CSV)
    if limit:
        # Ambil yang skor judulnya tertinggi kalau harus membatasi.
        # Lebih baik 3.000 artikel paling relevan daripada 3.000 acak.
        df = df.sort_values("title_score", ascending=False).head(limit)
        print(f"Dibatasi ke {limit:,} artikel dengan skor judul tertinggi")

    done_urls = set()
    for f in ARTICLE_CKPT.glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line:
                done_urls.add(json.loads(line).get("url"))

    todo = df[~df["url"].isin(done_urls)]
    print(f"Sudah selesai: {len(done_urls):,} | Sisa: {len(todo):,}\n")

    buffer, batch_no = [], int(time.time())
    failed = 0

    for i, row in enumerate(todo.itertuples(), 1):
        html = get_html(row.url, max_retry=2)
        if html:
            rec = parse_article(html, row.url)
            rec["index_date"] = row.date
            rec["title_score"] = row.title_score
            rec["matched_terms"] = row.matched_terms
            buffer.append(rec)
        else:
            failed += 1

        if i % 200 == 0 or i == len(todo):
            ckpt = ARTICLE_CKPT / f"batch_{batch_no}_{i}.jsonl"
            with ckpt.open("w", encoding="utf-8") as f:
                for r in buffer:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"  {i:,}/{len(todo):,} selesai | gagal: {failed} | -> {ckpt.name}")
            buffer = []

        polite_sleep(fast=True)

    # -- gabungkan semua checkpoint --
    rows = []
    for f in ARTICLE_CKPT.glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line:
                rows.append(json.loads(line))

    out = pd.DataFrame(rows).drop_duplicates(subset=["url"])

    # Samakan skema kolom dengan yang diharapkan preprocess_news.py,
    # supaya pipeline hilir tidak perlu diubah sama sekali.
    out["article_id"] = out["url"]
    out["type"] = "article"
    out["search_keyword"] = out.get("matched_terms", "")
    out["keyword_group"] = "html_sitemap"
    if "section" not in out:
        out["section"] = ""

    # Gabungkan deskripsi dan isi artikel. Isi dipotong 2.000 karakter:
    # paragraf pembuka berita memuat inti peristiwa, sisanya konteks dan
    # kutipan yang justru menambah noise untuk tugas klasifikasi harian.
    out["description"] = (
        out.get("description", "").fillna("")
        + " "
        + out.get("body", "").fillna("").str.slice(0, 2000)
    ).str.strip()

    out.to_csv(C.CNBC_RAW_CSV, index=False)

    print("\n" + "=" * 55)
    print(f"  Artikel terkumpul : {len(out):,}")
    print(f"  Punya isi artikel : {out['body'].notna().sum():,}")
    print(f"  Punya timestamp   : {out['published'].notna().sum():,}")
    print(f"  Tersimpan         : {C.CNBC_RAW_CSV}")
    print("=" * 55)
    print("\n  Lanjutkan dengan: python preprocess_news.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--stage1", action="store_true", help="panen indeks arsip")
    ap.add_argument("--stage2", action="store_true", help="filter judul")
    ap.add_argument("--stage3", action="store_true", help="panen artikel")
    ap.add_argument("--limit-articles", type=int, default=None)
    a = ap.parse_args()

    if a.probe:
        run_probe()
    elif a.stage1:
        run_stage1()
    elif a.stage2:
        run_stage2()
    elif a.stage3:
        run_stage3(a.limit_articles)
    else:
        ap.print_help()