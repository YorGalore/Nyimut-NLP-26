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

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from xgboost import XGBClassifier

import config as C

TRAIN_FRAC = 0.70
VALID_FRAC = 0.15
# sisa 0.15 -> test

VOLATILITY_LABELS = ["low", "medium", "high"]

# fitur harga yang SAMA dipakai XGBoost tanpa NLP (train_baseline_ts.py) dan
# XGBoost + TF-IDF + LM (train_combined.py) -- supaya selisih akurasinya murni
# efek fitur NLP, bukan beda fitur harga.
#
# KENAPA ADA known4_* DAN vol_if_*:
# target realized_vol(t) = std(r[t-4..t]) -- 4 dari 5 return di window itu
# SUDAH diketahui sebelum hari t, cuma r[t] yang belum. Makanya fitur yang
# paling informatif adalah ringkasan 4 return itu (bukan lag1_realized_vol,
# yang malah membawa r[t-5] -- return yang sudah keluar dari window target).
# vol_if_r0 = realized_vol(t) kalau r[t] = 0; vol_if_rtyp_* = kalau |r[t]|
# sebesar median |r| historis (naik / turun). Semua cuma pakai data < t.
PRICE_FEATURES = [
    "lag1_log_return", "lag2_log_return", "lag3_log_return", "lag4_log_return",
    "known4_mean", "known4_std", "vol_if_r0", "vol_if_rtyp_pos", "vol_if_rtyp_neg",
    "lag1_volatility_class_enc",
]

# fitur sentimen Loughran-McDonald per hari -- SAMA dipakai train_tfidf.py &
# train_combined.py. Pakai RATA-RATA PER ARTIKEL (bukan jumlah): jumlah artikel
# per hari berubah antar periode (rata2 3,9/hari di train vs 8,0 di valid, diduga
# karena cakupan scraping), jadi lm_*_sum ikut membesar walau nada beritanya
# sama. Rata-rata cuma mengukur NADA -- sejalan dgn Keputusan 18 (normalisasi
# volume berita). Lihat docs/keputusan.md.
LM_FEATURES = ["mean_lm_polarity", "lm_positive_mean", "lm_negative_mean"]

# grid kecil buat tuning -- dipilih berdasarkan akurasi VALID, dites ke test
# cuma SEKALI pakai kombinasi terbaik (bukan pilih2 sambil intip test).
# Dipakai SEMUA model XGBoost supaya masing-masing dapat kesempatan tuning yang sama.
XGB_GRID = [
    {"n_estimators": n, "max_depth": d, "learning_rate": lr}
    for n in (100, 200, 400)
    for d in (2, 3, 4)
    for lr in (0.03, 0.05, 0.1)
]


def add_price_features(df):
    """Fitur harga turunan log_return -- df HARUS deret kalender hari kerja lengkap & urut."""
    r = df["log_return"]
    df["lag4_log_return"] = r.shift(4)
    known = pd.concat([r.shift(i) for i in (1, 2, 3, 4)], axis=1)
    df["known4_mean"] = known.mean(axis=1, skipna=False)
    df["known4_std"] = known.std(axis=1, skipna=False)

    def vol_if(r_t):
        return np.std(np.column_stack([known.to_numpy(), r_t]), axis=1, ddof=1)

    typical = r.abs().expanding().median().shift(1).to_numpy()
    df["vol_if_r0"] = vol_if(np.zeros(len(df)))
    df["vol_if_rtyp_pos"] = vol_if(typical)
    df["vol_if_rtyp_neg"] = vol_if(-typical)
    return df


def tune_xgb(X_train, y_train_enc, X_valid, y_valid, X_test, encoder, log):
    """
    Coba semua kombinasi di XGB_GRID, PILIH berdasarkan akurasi VALID --
    test SAMA SEKALI tidak dilihat selama memilih. Kombinasi terbaik baru
    dites ke test SEKALI di akhir. Ini gunanya split 70/15/15 dibanding
    80/20: ada ruang buat coba-coba tanpa mengintip test.
    """
    best_acc, best_params, best_clf = -1, None, None
    for params in XGB_GRID:
        clf = XGBClassifier(**params, eval_metric="mlogloss", random_state=42)
        clf.fit(X_train, y_train_enc)
        pred_valid = encoder.inverse_transform(clf.predict(X_valid))
        acc = accuracy_score(y_valid, pred_valid)
        if acc > best_acc:
            best_acc, best_params, best_clf = acc, params, clf

    log(f"Hyperparameter terbaik (dipilih dari {len(XGB_GRID)} kombinasi via akurasi VALID): {best_params}")
    log(f"Akurasi valid dengan kombinasi ini: {best_acc:.3f}")
    pred_valid = encoder.inverse_transform(best_clf.predict(X_valid))
    pred_test = encoder.inverse_transform(best_clf.predict(X_test))
    return best_clf, pred_valid, pred_test


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
    # astype(float) WAJIB: tanpa ini kolomnya ikut ber-dtype category (warisan
    # pd.cut), dan XGBoost membacanya sebagai kategori TANPA urutan kalau diberi
    # DataFrame, tapi sebagai angka kalau diberi numpy array (train_combined.py)
    # -- fitur yang sama jadi diperlakukan beda antar model.
    df["lag1_volatility_class_enc"] = df["lag1_volatility_class"].map(ordinal_map).astype(float)

    # fitur harga turunan juga dihitung di kalender lengkap (alasan sama dgn lag1 di atas)
    df = add_price_features(df)

    # --- BARU SEKARANG filter ke hari yang punya berita ----------------------
    df = df[df["n_news"] > 0]
    # n_news > 0 dijamin di sini, jadi pembagian aman (tidak ada bagi nol)
    df["lm_positive_mean"] = df["lm_positive_sum"] / df["n_news"]
    df["lm_negative_mean"] = df["lm_negative_sum"] / df["n_news"]
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
