import bisect
import numpy as np
import pandas as pd
import config as C


def build_assigner(trading_dates):
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

    # n_tokens tidak disimpan di news_tfidf_clean.csv (dihitung ulang dari text_norm (title_clean/text_clean sudah tidak ada, itu jalur BERT))
    news["n_tokens"] = news["text_norm"].fillna("").str.split().str.len()

    trading_dates = sorted(kurs["date"].dt.date.unique())
    print(f"Hari kerja BI terdeteksi dari JISDOR: {len(trading_dates)} hari")

    # tetapkan target_date untuk tiap berita
    assign = build_assigner(trading_dates)
    news["target_date"] = news["published_wib"].apply(assign)

    before = len(news)
    news = news.dropna(subset=["target_date"])
    print(f"Berita dengan target valid: {len(news):,} dari {before:,}")

    news["target_date"] = pd.to_datetime(news["target_date"])

    # penanda apakah berita jatuh di luar jam perdagangan
    news["is_offhours"] = (
        (news["published_wib"].dt.dayofweek >= 5)
        | (news["published_wib"].dt.hour >= C.ALIGNMENT_CUTOFF_HOUR)
    )
    # jarak antara terbit dan fixing target, semakin jauh, semakin lemah efeknya
    news["hours_to_fixing"] = (
        news["target_date"]
        + pd.Timedelta(hours=C.ALIGNMENT_CUTOFF_HOUR)
        - news["published_wib"].dt.tz_localize(None)
    ).dt.total_seconds() / 3600


    # varian lag-1 untuk uji robustness di Tugas 2
    next_map = {d: trading_dates[i + 1] for i, d in enumerate(trading_dates[:-1])}
    news["target_date_lag1"] = pd.to_datetime(
        news["target_date"].dt.date.map(next_map)
    )

    news.to_csv(C.NEWS_TFIDF_CSV, index=False)
    print(f"news_tfidf_clean.csv diperbarui dengan kolom target_date")

    # agregasi ke level harian
    # kolom lm_* datang dari sentiment_lexicon.py (jalan SEBELUM align.py).
    # Kalau belum pernah dijalankan, error di sini -- itu sengaja, supaya
    # ketahuan urutan scriptnya salah, bukan diam-diam skip kolom sentimen.
    daily = (
        news.groupby("target_date")
        .agg(
            n_news=("url", "count"),
            mean_relevance=("relevance_score", "mean"),
            max_relevance=("relevance_score", "max"),
            mean_tokens=("n_tokens", "mean"),
            pct_offhours=("is_offhours", "mean"),
            mean_lm_polarity=("lm_polarity", "mean"),
            lm_positive_sum=("lm_positive", "sum"),
            lm_negative_sum=("lm_negative", "sum"),
            text_norm_concat=("text_norm", lambda s: " ".join(s.astype(str))),
        )
        .reset_index()
        .rename(columns={"target_date": "date"})
    )

    # left joindari sisi kurs
    merged = kurs.merge(daily, on="date", how="left")
    merged["n_news"] = merged["n_news"].fillna(0).astype(int)
    merged["text_norm_concat"] = merged["text_norm_concat"].fillna("")
    merged["lm_positive_sum"] = merged["lm_positive_sum"].fillna(0)
    merged["lm_negative_sum"] = merged["lm_negative_sum"].fillna(0)
    # mean_lm_polarity SENGAJA dibiarkan NaN di hari tanpa berita (bukan 0) --
    # 0 berarti "netral", NaN berarti "tidak ada sinyal sama sekali". dataset_split.py
    # sudah membuang hari n_news=0 sebelum modeling, jadi NaN ini tidak masalah.

    # lebar jendela berita yang mengalir ke hari ini
    merged["window_hours"] = merged["gap_days"].fillna(1) * 24
    merged.to_csv(C.ALIGNED_DAILY_CSV, index=False)

    # cek, angka-angka ini langsung dipakai di laporan
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

    # dua baris di bawah ditampilkan berdampingan.
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