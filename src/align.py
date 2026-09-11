"""
align.py
========
Menyelaraskan berita (24/7) dengan kurs JISDOR (hanya hari kerja BI).
news_clean.csv + kurs_clean.csv -> news_clean.csv (+kolom) & aligned_daily.csv

DASAR ATURANNYA
---------------
Fakta 1: timestamp CNBC dalam UTC; pasar acuan kita di WIB (UTC+7).

Fakta 2 (ini kuncinya): JISDOR BUKAN kurs penutupan. JISDOR adalah kurs
referensi yang dihitung dari transaksi antarbank pada jendela 08:00-09:45 WIB
dan dipublikasikan pukul 10:00 WIB setiap hari kerja Bank Indonesia.

Jadi pertanyaan penyelarasannya bukan "berita ini tanggal berapa", tetapi:
"berita ini terbit SEBELUM atau SESUDAH jendela pembentukan harga?"

ATURAN YANG KAMI TETAPKAN
-------------------------
  1. Konversi published_utc -> WIB.
  2. Cutoff = 08:00 WIB.
       terbit < 08:00 WIB  -> berpotensi memengaruhi fixing HARI ITU
       terbit >= 08:00 WIB -> baru memengaruhi fixing hari kerja BERIKUTNYA
  3. Kalau tanggal hasilnya bukan hari kerja BI (akhir pekan / libur nasional /
     cuti bersama), GULIRKAN MAJU ke hari kerja BI terdekat berikutnya.

KENAPA CUTOFF 08:00 DAN BUKAN 10:00?
Berita pukul 09:30 memang terbit sebelum publikasi jam 10:00, tetapi
informasinya sudah sebagian terserap ke dalam transaksi yang membentuk fixing
tersebut. Memakainya sebagai prediktor untuk fixing hari itu = look-ahead
bias yang halus. 08:00 adalah pilihan konservatif.

KENAPA ROLL-FORWARD, BUKAN ROLL-BACKWARD ATAU DIBUANG?
- Backward mustahil: informasi tidak bisa memengaruhi harga di masa lalu.
- Membuang berita akhir pekan berarti membuang ~28% korpus -- dan justru
  peristiwa akhir pekan (invasi, kudeta, keputusan OPEC) yang paling
  menggerakkan pasar.

KETERBATASAN YANG KAMI AKUI (wajib ditulis di laporan):
Hari Senin menerima jendela ~72 jam (Jumat 08:00 -> Senin 08:00), sedangkan
Rabu hanya 24 jam. Volume berita Senin jadi ~3x lipat. Karena itu kolom
n_news dan window_hours disimpan agar bisa dinormalisasi di Tugas 2.

Kalender hari kerja BI TIDAK diambil dari library hari libur. Kalender itu
diturunkan langsung dari himpunan tanggal yang ada di kurs_clean.csv.
"""

import bisect

import numpy as np
import pandas as pd

import config as C


def build_assigner(trading_dates):
    """
    Membuat fungsi yang memetakan satu timestamp WIB -> tanggal fixing target.

    trading_dates: list tanggal (datetime.date) terurut, diturunkan dari JISDOR.
    Pencarian memakai bisect (binary search) -- O(log n) per berita.
    Dengan puluhan ribu berita, loop linier akan terasa lambat.
    """
    dates = sorted(trading_dates)

    def assign(ts_wib):
        if pd.isna(ts_wib):
            return pd.NaT

        # Langkah 1: terapkan aturan cutoff
        candidate = ts_wib.date()
        if ts_wib.hour >= C.ALIGNMENT_CUTOFF_HOUR:
            candidate = (ts_wib + pd.Timedelta(days=1)).date()

        # Langkah 2: gulirkan maju ke hari kerja BI terdekat >= candidate
        idx = bisect.bisect_left(dates, candidate)
        if idx >= len(dates):
            return pd.NaT   # berita setelah fixing terakhir -> tidak punya target
        return dates[idx]

    return assign


def main():
    news = pd.read_csv(C.NEWS_CLEAN_CSV)
    kurs = pd.read_csv(C.KURS_CLEAN_CSV)

    news["published_wib"] = pd.to_datetime(news["published_wib"], errors="coerce")
    kurs["date"] = pd.to_datetime(kurs["date"], errors="coerce")

    trading_dates = sorted(kurs["date"].dt.date.unique())
    print(f"Hari kerja BI terdeteksi dari JISDOR: {len(trading_dates)} hari")

    # ------------------------------------------------------------------
    # 1. Tetapkan target_date untuk tiap berita
    # ------------------------------------------------------------------
    assign = build_assigner(trading_dates)
    news["target_date"] = news["published_wib"].apply(assign)

    before = len(news)
    news = news.dropna(subset=["target_date"])
    print(f"Berita dengan target valid: {len(news):,} dari {before:,}")

    news["target_date"] = pd.to_datetime(news["target_date"])

    # Penanda apakah berita jatuh di luar jam perdagangan.
    # Berguna sebagai fitur: berita "off-hours" sering punya karakter berbeda.
    news["is_offhours"] = (
        (news["published_wib"].dt.dayofweek >= 5)
        | (news["published_wib"].dt.hour >= C.ALIGNMENT_CUTOFF_HOUR)
    )
    # Jarak antara terbit dan fixing target -- semakin jauh, semakin lemah efeknya
    news["hours_to_fixing"] = (
        news["target_date"]
        + pd.Timedelta(hours=C.ALIGNMENT_CUTOFF_HOUR)
        - news["published_wib"].dt.tz_localize(None)
    ).dt.total_seconds() / 3600

    # ------------------------------------------------------------------
    # 2. Varian lag-1 untuk uji robustness di Tugas 2
    # ------------------------------------------------------------------
    # Nol usaha tambahan sekarang, tapi memungkinkan perbandingan
    # reaksi H+0 vs H+1 nanti tanpa mengulang alignment.
    next_map = {d: trading_dates[i + 1] for i, d in enumerate(trading_dates[:-1])}
    news["target_date_lag1"] = pd.to_datetime(
        news["target_date"].dt.date.map(next_map)
    )

    news.to_csv(C.NEWS_CLEAN_CSV, index=False)
    print(f"news_clean.csv diperbarui dengan kolom target_date")

    # ------------------------------------------------------------------
    # 3. Agregasi ke level harian
    # ------------------------------------------------------------------
    # news_clean.csv (level artikel) TETAP disimpan dan tidak dibuang --
    # Tugas 3 (multimodal) membutuhkan granularitas per artikel.
    daily = (
        news.groupby("target_date")
        .agg(
            n_news=("article_id", "count"),
            mean_relevance=("relevance_score", "mean"),
            max_relevance=("relevance_score", "max"),
            mean_tokens=("n_tokens", "mean"),
            pct_offhours=("is_offhours", "mean"),
            headlines=("title_clean", lambda s: " || ".join(s.astype(str))),
            text_concat=("text_clean", lambda s: " ".join(s.astype(str))),
            text_norm_concat=("text_norm", lambda s: " ".join(s.astype(str))),
        )
        .reset_index()
        .rename(columns={"target_date": "date"})
    )

    # LEFT JOIN dari sisi kurs: hari kerja BI yang tidak punya berita tetap
    # muncul sebagai baris dengan n_news = 0. Ini disengaja -- ketiadaan berita
    # juga informasi, dan menghapusnya akan merusak kontinuitas deret waktu.
    merged = kurs.merge(daily, on="date", how="left")
    merged["n_news"] = merged["n_news"].fillna(0).astype(int)
    for col in ["headlines", "text_concat", "text_norm_concat"]:
        merged[col] = merged[col].fillna("")

    # Lebar jendela berita yang mengalir ke hari ini. Wajib dipakai sebagai
    # kontrol saat modeling, karena Senin punya jendela ~3x lebih lebar.
    merged["window_hours"] = merged["gap_days"].fillna(1) * 24

    merged.to_csv(C.ALIGNED_DAILY_CSV, index=False)

    # ------------------------------------------------------------------
    # 4. Sanity check -- angka-angka ini langsung dipakai di laporan
    # ------------------------------------------------------------------
    cov = (merged["n_news"] > 0).mean() * 100
    merged["dow"] = merged["date"].dt.day_name()

    print("\n" + "=" * 58)
    print("HASIL PENYELARASAN")
    print("=" * 58)
    print(f"  Hari kerja BI                  : {len(merged):,}")
    print(f"  Hari dengan >= 1 berita        : {cov:.1f}%")
    print(f"  Rata-rata berita per hari      : {merged['n_news'].mean():.1f}")
    print(f"  Median berita per hari         : {merged['n_news'].median():.0f}")
    print(f"  Hari tanpa berita sama sekali  : {(merged['n_news'] == 0).sum()}")
    print("\n  Rata-rata jumlah berita per hari dalam seminggu")
    print("  (Senin WAJIB lebih tinggi -- itu bukti aturan roll-forward bekerja):")
    print(
        merged.groupby("dow")["n_news"].mean()
        .reindex(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
        .round(1).to_string()
    )
    print(f"\n  Tersimpan: {C.ALIGNED_DAILY_CSV}")

    if cov < 90:
        print("\n  PERINGATAN: cakupan < 90%. Leksikon keyword terlalu sempit.")
        print("  Tambahkan keyword di config.py lalu jalankan ulang scraper.")


if __name__ == "__main__":
    main()