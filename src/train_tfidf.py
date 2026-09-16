"""
train_tfidf.py
===============
Baseline TF-IDF + Logistic Regression: memprediksi arah kurs JISDOR
(up/down/flat) dari teks berita geopolitik yang terbit di jendela hari itu.
data/processed/aligned_daily.csv -> logs/train_tfidf_report.txt

UNIT ANALISIS: PER HARI, BUKAN PER ARTIKEL
-------------------------------------------
Target (`direction`) adalah label harian (satu label per fixing JISDOR).
Karena itu fitur teksnya juga harus per hari: `text_norm_concat` di
aligned_daily.csv (gabungan text_norm semua artikel yang jatuh di jendela
hari itu, hasil kerja align.py). Bukan per-artikel -- itu granularitas yang
salah untuk target harian.

HARI TANPA BERITA DIBUANG DARI TRAINING
----------------------------------------
align.py sengaja mempertahankan hari kerja BI tanpa berita (n_news=0,
text_norm_concat="") supaya deret waktu kurs tetap utuh untuk Tugas 2/3.
Tapi untuk model TF-IDF, dokumen kosong tidak punya sinyal apa pun --
disertakan hanya akan menambah kelas mayoritas secara artifisial dan
mencemari classification report. Baris ini di-drop DI SINI, bukan di
align.py, supaya file itu tetap dipakai bersama Tugas 2/3.

SPLIT BERDASARKAN WAKTU, BUKAN ACAK
-------------------------------------
Ini deret waktu. Random split akan membiarkan model "mengintip" kosakata
dari peristiwa masa depan (mis. kata "houthi" cuma muncul di 2024) untuk
memprediksi masa lalu -- look-ahead bias yang sama seperti yang dihindari
align.py. Split 80/20 kronologis: 20% hari TERAKHIR jadi test set.

KENAPA class_weight="balanced"?
"flat" cuma ~11% dari data (zona mati log_return < FLAT_THRESHOLD).
Tanpa pembobotan, model paling gampang menang dengan selalu menebak "up"
(kelas mayoritas) dan skor recall "flat"/"down" nyaris nol.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.dummy import DummyClassifier

import config as C

TEST_FRACTION = 0.2
MIN_DF = 5
MAX_DF = 0.8
NGRAM_RANGE = (1, 2)
MAX_FEATURES = 5000

LOG_DIR = C.ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = LOG_DIR / "train_tfidf_report.txt"


def main():
    lines = []

    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    df = pd.read_csv(C.ALIGNED_DAILY_CSV)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    n_total = len(df)
    df = df[df["n_news"] > 0].reset_index(drop=True)
    log(f"Hari kerja BI total          : {n_total:,}")
    log(f"Hari dibuang (n_news = 0)    : {n_total - len(df):,}")
    log(f"Hari dipakai untuk modeling  : {len(df):,}")
    log()

    log("Distribusi kelas (seluruh hari yang dipakai):")
    log(df["direction"].value_counts().to_string())
    log()

    # --- split kronologis -----------------------------------------------
    split_idx = int(len(df) * (1 - TEST_FRACTION))
    train, test = df.iloc[:split_idx], df.iloc[split_idx:]
    log(f"Train: {len(train):,} hari ({train['date'].min().date()} .. {train['date'].max().date()})")
    log(f"Test : {len(test):,} hari ({test['date'].min().date()} .. {test['date'].max().date()})")
    log()

    X_train_text = train["text_norm_concat"].fillna("")
    X_test_text = test["text_norm_concat"].fillna("")
    y_train, y_test = train["direction"], test["direction"]

    # --- vectorize --------------------------------------------------------
    vectorizer = TfidfVectorizer(
        min_df=MIN_DF, max_df=MAX_DF, ngram_range=NGRAM_RANGE,
        max_features=MAX_FEATURES,
    )
    X_train = vectorizer.fit_transform(X_train_text)
    X_test = vectorizer.transform(X_test_text)
    log(f"Ukuran vocabulary TF-IDF: {len(vectorizer.vocabulary_):,}")
    log()

    # --- baseline: selalu tebak kelas mayoritas ---------------------------
    dummy = DummyClassifier(strategy="most_frequent")
    dummy.fit(X_train, y_train)
    dummy_acc = accuracy_score(y_test, dummy.predict(X_test))

    # --- model utama --------------------------------------------------------
    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf.fit(X_train, y_train)
    pred = clf.predict(X_test)
    acc = accuracy_score(y_test, pred)

    log("=" * 60)
    log("HASIL BASELINE TF-IDF + LOGISTIC REGRESSION")
    log("=" * 60)
    log(f"Akurasi dummy (selalu tebak kelas mayoritas) : {dummy_acc:.3f}")
    log(f"Akurasi Logistic Regression                  : {acc:.3f}")
    log()
    log("Classification report (test set):")
    log(classification_report(y_test, pred, zero_division=0))
    log("Confusion matrix (baris=aktual, kolom=prediksi), label urut " + str(sorted(y_test.unique())))
    log(confusion_matrix(y_test, pred, labels=sorted(y_test.unique())))
    log()

    # --- term paling berpengaruh per kelas (untuk laporan) ------------------
    feature_names = np.array(vectorizer.get_feature_names_out())
    log("Term dengan bobot koefisien tertinggi per kelas:")
    for i, cls in enumerate(clf.classes_):
        top_idx = np.argsort(clf.coef_[i])[-15:][::-1]
        log(f"  [{cls}] " + ", ".join(feature_names[top_idx]))
    log()

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log(f"Laporan tersimpan: {REPORT_PATH}")


if __name__ == "__main__":
    main()
