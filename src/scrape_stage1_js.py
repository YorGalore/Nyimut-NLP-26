import argparse
import json
import re
import time
from datetime import date, timedelta
import pandas as pd
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

import config as C

# nama bulan ditulis manual
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

INDEX_CSV = C.DATA_RAW / "cnbc_index.csv"
CKPT_DIR = C.CHECKPOINT_DIR / "index"
CKPT_DIR.mkdir(parents=True, exist_ok=True)

RE_ART = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/[a-z0-9\-]+\.html")

# resource yang diblokir
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
    return f"https://www.cnbc.com/site-map/articles/{d.year}/{MONTHS[d.month-1]}/{d.day}/"


def should_block(route):
    req = route.request
    if req.resource_type in BLOCK_TYPES:
        return route.abort()
    if any(h in req.url for h in BLOCK_URL_HINTS):
        return route.abort()
    return route.continue_()


def scrape_day(page, d):
    # ambil semua link artikel untuk satu tanggal.
    url = archive_url(d)
    # selector yang spesifik ke tanggal halaman ini
    datepath = f"/{d.year}/{d.month:02d}/{d.day:02d}/"
    selector = f"a[href*='{datepath}']"

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except PWTimeout:
        return None  # none = gagal dimuat (beda dari [] = tidak ada artikel)

    try:
        page.wait_for_selector(selector, timeout=12000)
    except PWTimeout:
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
        # verifikasi ulang tanggalnya
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

    # kelompokkan tanggal per bulan -> checkpoint jadi 61 file
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
                    # satu kali percobaan ulang. Kegagalan biasanya sesaat.
                    time.sleep(3)
                    rows = scrape_day(page, day) or []
                month_rows.extend(rows)
                done_days += 1

            ckpt.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in month_rows),
                encoding="utf-8",
            )
            all_rows.extend(month_rows)

            # estimasi sisa waktu, dihitung dari kecepatan sebenarnya
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
