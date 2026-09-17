import argparse
import json
import random
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

import config as C


# lapisan http
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
    # Ambil HTML satu halaman, dengan retry dan backoff.
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
    time.sleep(random.uniform(0.4, 0.9) if fast else random.uniform(1.0, 2.0))

# pola url archive
URL_PATTERNS = {
    "month_name_cap": lambda d: f"https://www.cnbc.com/site-map/articles/{d.year}/{d.strftime('%B')}/{d.day}/",
    "month_name_low": lambda d: f"https://www.cnbc.com/site-map/articles/{d.year}/{d.strftime('%B').lower()}/{d.day}/",
    "month_num":      lambda d: f"https://www.cnbc.com/site-map/articles/{d.year}/{d.month}/{d.day}/",
    "month_num_pad":  lambda d: f"https://www.cnbc.com/site-map/articles/{d.year}/{d.month:02d}/{d.day:02d}/",
    "no_trailing":    lambda d: f"https://www.cnbc.com/site-map/articles/{d.year}/{d.strftime('%B')}/{d.day}",
}

# isi setelah --probe memberi tahu mana yang benar
ARCHIVE_PATTERN = "month_name_cap"

INDEX_CSV = C.DATA_RAW / "cnbc_index.csv"          # tahap 1
SHORTLIST_CSV = C.DATA_RAW / "cnbc_shortlist.csv"  # tahap 2
INDEX_CKPT = C.CHECKPOINT_DIR / "index"
ARTICLE_CKPT = C.CHECKPOINT_DIR / "articles"
INDEX_CKPT.mkdir(parents=True, exist_ok=True)
ARTICLE_CKPT.mkdir(parents=True, exist_ok=True)



# probe
def run_probe():
    # coba kelima pola URL pada satu tanggal, laporkan mana yang berhasil dan simpan HTML mentahnya supaya struktur tag bisa diperiksa manual
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


# collect judul
RE_ARTICLE_URL = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")

def parse_archive_page(html, day):
    # Parse satu halaman arsip harian -> daftar {title, url, date}.
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
    # loop semua tanggal dalam rentang tugas, checkpoint per BULAN, bukan per hari: 60 file, bukan 1.826.
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



# filter judul
def run_stage2():
    # skor semua judul dengan leksikon dari config.py, ambil yang lolos ambang
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



# panen artikel
# selector ditulis sebagai daftar kandidat berurutan
BODY_SELECTORS = [
    "div.ArticleBody-articleBody",
    "div[data-module='ArticleBody']",
    "div.group",
    "article",
]


def parse_article(html, url):
    # ekstrak 1 artikel
    soup = BeautifulSoup(html, "html.parser")
    rec = {"url": url}

    # lapis 1: JSON-LD 
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

    # lapis 2: meta tag
    def meta(prop):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return tag.get("content") if tag else None

    rec.setdefault("title", None)
    rec["title"] = rec.get("title") or meta("og:title")
    rec["description"] = rec.get("description") or meta("og:description")
    rec["published"] = rec.get("published") or meta("article:published_time")
    rec["section"] = meta("article:section") or meta("og:section")

    # lapis 3: selector css
    if not rec.get("body"):
        for sel in BODY_SELECTORS:
            node = soup.select_one(sel)
            if node:
                paras = [p.get_text(" ", strip=True) for p in node.find_all("p")]
                if len(paras) >= 3:
                    rec["body"] = " ".join(paras)
                    break

    return rec


def run_stage3(limit=None, index_file=None, out_csv=None, ckpt_dir=None):
    # fetch tiap artikel di shortlist, checkpoint per 200 artikel
    src = Path(index_file) if index_file else SHORTLIST_CSV
    out_path = Path(out_csv) if out_csv else C.CNBC_RAW_CSV
    ckptdir = Path(ckpt_dir) if ckpt_dir else ARTICLE_CKPT
    ckptdir.mkdir(parents=True, exist_ok=True)

    print(f"Input      : {src}")
    print(f"Checkpoint : {ckptdir}")
    print(f"Output     : {out_path}\n")

    df = pd.read_csv(src)
    if limit:
        # ambil yang skor judulnya tertinggi kalau harus membatasi
        df = df.sort_values("title_score", ascending=False).head(limit)
        print(f"Dibatasi ke {limit:,} artikel dengan skor judul tertinggi")

    done_urls = set()
    for f in ckptdir.glob("*.jsonl"):
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
            ckpt = ckptdir / f"batch_{batch_no}_{i}.jsonl"
            with ckpt.open("w", encoding="utf-8") as f:
                for r in buffer:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"  {i:,}/{len(todo):,} selesai | gagal: {failed} | -> {ckpt.name}")
            buffer = []

        polite_sleep(fast=True)

    # gabung semua checkpoint jadi satu CSV, buang artikel berbayar, samakan skema kolom
    rows = []
    for f in ckptdir.glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line:
                rows.append(json.loads(line))

    out = pd.DataFrame(rows).drop_duplicates(subset=["url"])

    # buang konten berbayar
    sec = out.get("section", pd.Series("", index=out.index)).fillna("").str.lower()
    berbayar = sec.str.contains("pro:|investing club", regex=True)
    n_berbayar = int(berbayar.sum())
    out = out[~berbayar].copy()

    # samakan skema kolom dengan yang diharapkan preprocess_news.py,
    # supaya pipeline hilir tidak perlu diubah sama sekali.
    out["article_id"] = out["url"]
    out["type"] = "article"
    out["search_keyword"] = out.get("matched_terms", "")
    out["keyword_group"] = "html_sitemap"
    if "section" not in out:
        out["section"] = ""

    out["description"] = (
        out.get("description", "").fillna("")
        + " "
        + out.get("body", "").fillna("").str.slice(0, 2000)
    ).str.strip()

    out.to_csv(out_path, index=False)

    print("\n" + "=" * 55)
    print(f"  Dibuang (berbayar): {n_berbayar:,}")
    print(f"  Artikel terkumpul : {len(out):,}")
    print(f"  Punya isi artikel : {out['body'].notna().sum():,}")
    print(f"  Punya timestamp   : {out['published'].notna().sum():,}")
    print(f"  Tersimpan         : {out_path}")
    print("=" * 55)
    print("\n  Lanjutkan dengan: python preprocess_news.py")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--stage1", action="store_true", help="panen indeks arsip")
    ap.add_argument("--stage2", action="store_true", help="filter judul")
    ap.add_argument("--stage3", action="store_true", help="panen artikel")
    ap.add_argument("--limit-articles", type=int, default=None)
    ap.add_argument("--index-file", type=str, default=None,
                    help="input tahap 3 pengganti cnbc_shortlist.csv")
    ap.add_argument("--out-csv", type=str, default=None,
                    help="output tahap 3 pengganti CNBC_RAW_CSV")
    ap.add_argument("--ckpt-dir", type=str, default=None,
                    help="folder checkpoint tahap 3 pengganti checkpoints/articles")
    a = ap.parse_args()

    if a.probe:
        run_probe()
    elif a.stage1:
        run_stage1()
    elif a.stage2:
        run_stage2()
    elif a.stage3:
        run_stage3(a.limit_articles, a.index_file, a.out_csv, a.ckpt_dir)
    else:
        ap.print_help()