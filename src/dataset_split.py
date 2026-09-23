"""
dataset_split.py
=================
Split kronologis 70/15/15 (train/valid/test) + pelabelan volatility_class
BEBAS BOCOR -- dipakai bareng oleh SEMUA script training (train_tfidf.py,
train_baseline_ts.py, train_combined.py) supaya definisi split dan definisi
kelas volatility SAMA PERSIS di semua model, dan hasilnya bisa dibandingkan
apples-to-apples.

KENAPA AMBANG BATAS low/medium/high DI-FIT DARI TRAIN SAJA:
--------------------------------------------------------------------------
realized_vol (rolling std log_return, dihitung di preprocess_kurs.py) per
baris sendiri sudah aman -- cuma pakai histori KE BELAKANG. Tapi kalau
ambang batas (cutoff) low/medium/high dihitung pakai qcut dari SELURUH data
(termasuk valid & test), ambang batasnya "tahu" sebaran volatility masa
depan -- itu bocor, walau realized_vol sendiri tidak.

Analoginya sama persis kayak TfidfVectorizer: fit_transform di train,
transform DOANG (pakai vocab yang sudah dipelajari) di test. Di sini:
qcut (fit ambang batas) cuma di 70% data tertua, pd.cut (terapkan ambang
batas yang sama, tanpa dihitung ulang) ke train+valid+test sekaligus.

KENAPA BINNING DILAKUKAN SEBELUM DIPOTONG jadi train/valid/test:
--------------------------------------------------------------------------
lag1_volatility_class butuh label hari SEBELUMNYA. Kalau train/valid/test
dilabeli terpisah-pisah, baris PERTAMA di valid kehilangan lag1 dari baris
TERAKHIR di train (deretnya jadi bolong tepat di titik sambungan). Makanya:
label dulu SELURUH deret pakai ambang batas yang sudah di-fit, baru dipotong.
"""

import pandas as pd
import config as C

TRAIN_FRAC = 0.70
VALID_FRAC = 0.15
# sisa 0.15 -> test

VOLATILITY_LABELS = ["low", "medium", "high"]


def build_dataset(required_cols=None):
    """
    Baca aligned_daily.csv, filter hari yang punya berita (n_news > 0) --
    supaya TF-IDF, LM, model harga-saja, dan model gabungan semua dievaluasi
    di himpunan hari yang SAMA PERSIS.

    required_cols: kolom tambahan yang wajib tidak-NaN (mis. fitur lag harga
    untuk train_baseline_ts.py/train_combined.py). realized_vol selalu wajib
    ada karena itu dasar volatility_class.

    Return: (train, valid, test) -- masing-masing DataFrame kronologis,
    sudah punya kolom volatility_class & lag1_volatility_class.
    """
    df = pd.read_csv(C.ALIGNED_DAILY_CSV)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # --- fit & terapkan volatility_class DI SELURUH KALENDER HARI KERJA,
    # SEBELUM filter n_news > 0 -- supaya lag1_volatility_class(t) merujuk ke
    # HARI KERJA SEBELUMNYA secara kalender (persis semantik lag1_realized_vol
    # / lag1_log_return di preprocess_kurs.py), BUKAN "hari BERITA sebelumnya".
    # Kalau filter n_news dilakukan DULU baru di-shift(1), shift-nya melompati
    # hari-hari tanpa berita (94 dari 1.202 hari) dan salah menunjuk ke hari
    # yang lebih jauh ke belakang -- bug yang sempat kejadian di sini.
    n_all = len(df)
    n_train_all = int(n_all * TRAIN_FRAC)
    train_vol = df["realized_vol"].iloc[:n_train_all].dropna()
    _, edges = pd.qcut(train_vol, 3, retbins=True, duplicates="drop")
    edges = edges.copy()
    edges[0], edges[-1] = -float("inf"), float("inf")  # jaga2 nilai valid/test di luar rentang train
    labels = VOLATILITY_LABELS[: len(edges) - 1]

    df["volatility_class"] = pd.cut(df["realized_vol"], bins=edges, labels=labels)
    df["lag1_volatility_class"] = df["volatility_class"].shift(1)
    # versi angka (low=0 < medium=1 < high=2) -- biar bisa dipakai XGBoost
    # sebagai FITUR, bukan cuma buat naive persistence. Ini fitur paling kuat
    # yang tadinya cuma "dibocorkan" ke naive, gak pernah dikasih ke XGBoost.
    ordinal_map = {label: i for i, label in enumerate(labels)}
    df["lag1_volatility_class_enc"] = df["lag1_volatility_class"].map(ordinal_map)

    # --- BARU SEKARANG filter ke hari yang punya berita ----------------------
    df = df[df["n_news"] > 0]
    required_cols = required_cols or []
    df = df.dropna(subset=["realized_vol"] + required_cols).reset_index(drop=True)

    n = len(df)
    n_train = int(n * TRAIN_FRAC)
    n_valid = int(n * VALID_FRAC)
    train = df.iloc[:n_train].reset_index(drop=True)
    valid = df.iloc[n_train : n_train + n_valid].reset_index(drop=True)
    test = df.iloc[n_train + n_valid :].reset_index(drop=True)
    return train, valid, test


def log_split_summary(log, train, valid, test):
    log("Distribusi kelas volatility_class (train, dipakai fit ambang batas):")
    log(train["volatility_class"].value_counts().to_string())
    log()
    log(f"Train: {len(train):,} hari ({train['date'].min().date()} .. {train['date'].max().date()})")
    log(f"Valid: {len(valid):,} hari ({valid['date'].min().date()} .. {valid['date'].max().date()})")
    log(f"Test : {len(test):,} hari ({test['date'].min().date()} .. {test['date'].max().date()})")
    log()
