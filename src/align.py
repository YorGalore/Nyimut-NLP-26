"""
align.py
========
Menyelaraskan berita (24/7) dengan kurs JISDOR (hanya hari kerja BI).
news_tfidf_clean.csv + kurs_clean.csv -> news_tfidf_clean.csv (+kolom) & aligned_daily.csv

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
Hari Senin menerima jendela ~63 jam (Jumat 08:00 -> Senin 08:00), sedangkan
hari lain cuma ~30 jam -- window_hours membuktikan roll-forward bekerja.
TAPI n_news mentah Senin TIDAK ikut ~2x lipat seperti dugaan awal: volume
publikasi CNBC di akhir pekan jauh lebih sepi (berita/jam Senin ~0.046,
hari lain ~0.11-0.13), jadi jendela lebih lebar tidak otomatis berarti
lebih banyak berita absolut. Karena itu JANGAN bandingkan n_news mentah
antar hari -- kolom n_news dan window_hours disimpan justru supaya bisa
dinormalisasi (n_news / window_hours) sebelum dibandingkan, baik di sini
maupun saat modeling Tugas 2.

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
    news = pd.read_csv(C.NEWS_TFIDF_CSV)
    kurs = pd.read_csv(C.KURS_CLEAN_CSV)

    news["published_wib"] = pd.to_datetime(news["published_wib"], errors="coerce")
    kurs["date"] = pd.to_datetime(kurs["date"], errors="coerce")

    # n_tokens tidak disimpan di news_tfidf_clean.csv -- dihitung ulang dari
    # text_norm (title_clean/text_clean sudah tidak ada, itu jalur BERT).
    news["n_tokens"] = news["text_norm"].fillna("").str.split().str.len()

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

    news.to_csv(C.NEWS_TFIDF_CSV, index=False)
    print(f"news_tfidf_clean.csv diperbarui dengan kolom target_date")

    # ------------------------------------------------------------------
    # 3. Agregasi ke level harian
    # ------------------------------------------------------------------
    # news_tfidf_clean.csv (level artikel) TETAP disimpan dan tidak dibuang --
    # Tugas 3 (multimodal) membutuhkan granularitas per artikel.
    # headlines/text_concat (dari title_clean/text_clean) sudah tidak ada di
    # sini -- itu jalur BERT, ditangani script terpisah milik rekan tim.
    daily = (
        news.groupby("target_date")
        .agg(
            n_news=("url", "count"),
            mean_relevance=("relevance_score", "mean"),
            max_relevance=("relevance_score", "max"),
            mean_tokens=("n_tokens", "mean"),
            pct_offhours=("is_offhours", "mean"),
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
    merged["text_norm_concat"] = merged["text_norm_concat"].fillna("")

    # Lebar jendela berita yang mengalir ke hari ini. Wajib dipakai sebagai
    # kontrol saat modeling, karena Senin punya jendela ~2x lebih lebar.
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

    # Bukti roll-forward yang benar adalah window_hours (lebar jendela waktu),
    # BUKAN n_news mentah -- n_news mentah dipengaruhi juga oleh volume
    # publikasi CNBC yang naik-turun per hari (weekend jauh lebih sepi),
    # jadi Senin tidak otomatis punya n_news tertinggi meski jendelanya
    # paling lebar. Makanya dua baris di bawah ditampilkan berdampingan.
    per_dow = merged.groupby("dow").agg(
        window_hours=("window_hours", "mean"),
        n_news=("n_news", "mean"),
    )
    per_dow["news_per_hour"] = per_dow["n_news"] / per_dow["window_hours"]
    print("\n  Per hari dalam seminggu (window_hours = bukti roll-forward,")
    print("  n_news mentah JANGAN dibandingkan langsung -- lihat news_per_hour):")
    print(
        per_dow.reindex(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
        .round(3).to_string()
    )
    print(f"\n  Tersimpan: {C.ALIGNED_DAILY_CSV}")

    if cov < 90:
        print("\n  PERINGATAN: cakupan < 90%. Leksikon keyword terlalu sempit.")
        print("  Tambahkan keyword di config.py lalu jalankan ulang scraper.")


if __name__ == "__main__":
    main()