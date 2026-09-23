"""
train_tfidf.py
===============
Dua jalur fitur NLP -> volatility_class (low/medium/high), dievaluasi
berdampingan pakai split kronologis 70/15/15 dari dataset_split.py:
  BASELINE A -- TF-IDF (text_norm_concat)
  BASELINE B -- Sentiment Lexicon Loughran-McDonald (mean_lm_polarity, dst)

Tiap baseline dilatih pakai DUA algoritma (Logistic Regression & XGBoost)
supaya perbandingan TF-IDF vs LM tidak bercampur sama perbandingan
algoritma -- kalau cuma satu algoritma dipakai buat satu fitur dan
algoritma lain buat fitur satunya, kita gak akan tahu apakah selisih
akurasi itu karena FITUR-nya beda atau ALGORITMA-nya beda. Dummy & Naive
persistence (lihat dataset_split.py) dilaporkan juga sebagai acuan
universal yang sama dipakai train_baseline_ts.py & train_combined.py.

TF-IDF DI-FIT DI TRAIN SAJA:
TfidfVectorizer.fit_transform() cuma dipanggil di train -- valid & test
cuma di-.transform() pakai vocabulary yang sudah dipelajari. Kalau di-fit
dari seluruh data, model "mengintip" kosakata dari peristiwa masa depan
(mis. kata yang cuma muncul di 2026) buat memprediksi masa lalu.
"""

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.dummy import DummyClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from xgboost import XGBClassifier

import config as C
from dataset_split import build_dataset, log_split_summary

MIN_DF = 5
MAX_DF = 0.8
NGRAM_RANGE = (1, 2)
MAX_FEATURES = 5000

LM_FEATURES = ["mean_lm_polarity", "lm_positive_sum", "lm_negative_sum"]

LOG_DIR = C.ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = LOG_DIR / "train_tfidf_report.txt"

MODEL_DIR = C.ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def report_block(log, name, y_valid, pred_valid, y_test, pred_test, labels):
    log(f"Akurasi valid : {accuracy_score(y_valid, pred_valid):.3f}")
    log(f"Akurasi test  : {accuracy_score(y_test, pred_test):.3f}")
    log()
    log("Classification report (TEST set):")
    log(classification_report(y_test, pred_test, zero_division=0))
    log("Confusion matrix TEST (baris=aktual, kolom=prediksi), label urut " + str(labels))
    log(confusion_matrix(y_test, pred_test, labels=labels))
    log()


def main():
    lines = []

    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    train, valid, test = build_dataset()
    log_split_summary(log, train, valid, test)

    labels = sorted(train["volatility_class"].unique())
    y_train, y_valid, y_test = train["volatility_class"], valid["volatility_class"], test["volatility_class"]
    encoder = LabelEncoder().fit(y_train)
    y_train_enc = encoder.transform(y_train)

    dummy = DummyClassifier(strategy="most_frequent")
    dummy.fit(train[["n_news"]], y_train)
    dummy_acc_test = accuracy_score(y_test, dummy.predict(test[["n_news"]]))

    # acuan universal: sama dipakai train_baseline_ts.py & train_combined.py
    naive_acc_test = accuracy_score(y_test, test["lag1_volatility_class"])

    def fit_xgb(X_train, X_valid, X_test):
        clf = XGBClassifier(
            n_estimators=200, max_depth=3, learning_rate=0.05,
            eval_metric="mlogloss", random_state=42,
        )
        clf.fit(X_train, y_train_enc)
        pred_valid = encoder.inverse_transform(clf.predict(X_valid))
        pred_test = encoder.inverse_transform(clf.predict(X_test))
        return clf, pred_valid, pred_test

    # =========================================================================
    # BASELINE A: TF-IDF -- Logistic Regression & XGBoost
    # =========================================================================
    vectorizer = TfidfVectorizer(
        min_df=MIN_DF, max_df=MAX_DF, ngram_range=NGRAM_RANGE,
        max_features=MAX_FEATURES,
    )
    X_train_tfidf = vectorizer.fit_transform(train["text_norm_concat"].fillna(""))
    X_valid_tfidf = vectorizer.transform(valid["text_norm_concat"].fillna(""))
    X_test_tfidf = vectorizer.transform(test["text_norm_concat"].fillna(""))
    log(f"Ukuran vocabulary TF-IDF (fit dari train saja): {len(vectorizer.vocabulary_):,}")
    log()

    clf_tfidf_lr = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf_tfidf_lr.fit(X_train_tfidf, y_train)
    pred_valid_tfidf_lr = clf_tfidf_lr.predict(X_valid_tfidf)
    pred_test_tfidf_lr = clf_tfidf_lr.predict(X_test_tfidf)

    log("=" * 60)
    log("BASELINE A1 -- TF-IDF + LOGISTIC REGRESSION -> volatility_class")
    log("=" * 60)
    report_block(log, "tfidf_lr", y_valid, pred_valid_tfidf_lr, y_test, pred_test_tfidf_lr, labels)

    feature_names = np.array(vectorizer.get_feature_names_out())
    log("Term dengan bobot koefisien tertinggi per kelas (Logistic Regression):")
    for i, cls in enumerate(clf_tfidf_lr.classes_):
        top_idx = np.argsort(clf_tfidf_lr.coef_[i])[-15:][::-1]
        log(f"  [{cls}] " + ", ".join(feature_names[top_idx]))
    log()

    clf_tfidf_xgb, pred_valid_tfidf_xgb, pred_test_tfidf_xgb = fit_xgb(X_train_tfidf, X_valid_tfidf, X_test_tfidf)
    log("=" * 60)
    log("BASELINE A2 -- TF-IDF + XGBOOST -> volatility_class")
    log("=" * 60)
    report_block(log, "tfidf_xgb", y_valid, pred_valid_tfidf_xgb, y_test, pred_test_tfidf_xgb, labels)

    joblib.dump(vectorizer, MODEL_DIR / "tfidf_vectorizer.pkl")
    joblib.dump(clf_tfidf_lr, MODEL_DIR / "tfidf_logreg.pkl")
    joblib.dump(clf_tfidf_xgb, MODEL_DIR / "tfidf_xgb.pkl")
    log(f"Tersimpan: {MODEL_DIR / 'tfidf_vectorizer.pkl'}, tfidf_logreg.pkl, tfidf_xgb.pkl")
    log()

    # =========================================================================
    # BASELINE B: Sentiment Lexicon (Loughran-McDonald) -- Logistic Regression & XGBoost
    # =========================================================================
    scaler = StandardScaler()
    X_train_lm = scaler.fit_transform(train[LM_FEATURES].fillna(0))
    X_valid_lm = scaler.transform(valid[LM_FEATURES].fillna(0))
    X_test_lm = scaler.transform(test[LM_FEATURES].fillna(0))

    clf_lm_lr = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf_lm_lr.fit(X_train_lm, y_train)
    pred_valid_lm_lr = clf_lm_lr.predict(X_valid_lm)
    pred_test_lm_lr = clf_lm_lr.predict(X_test_lm)

    log("=" * 60)
    log("BASELINE B1 -- SENTIMENT LEXICON (LM) + LOGISTIC REGRESSION -> volatility_class")
    log("=" * 60)
    log(f"Fitur dipakai: {LM_FEATURES}")
    report_block(log, "lm_lr", y_valid, pred_valid_lm_lr, y_test, pred_test_lm_lr, labels)

    log("Koefisien per kelas (arah pengaruh tiap fitur, setelah scaling):")
    for i, cls in enumerate(clf_lm_lr.classes_):
        coefs = ", ".join(f"{f}={c:+.3f}" for f, c in zip(LM_FEATURES, clf_lm_lr.coef_[i]))
        log(f"  [{cls}] {coefs}")
    log()

    # XGBoost berbasis pohon -- gak butuh scaling, pakai nilai mentah
    X_train_lm_raw = train[LM_FEATURES].fillna(0)
    X_valid_lm_raw = valid[LM_FEATURES].fillna(0)
    X_test_lm_raw = test[LM_FEATURES].fillna(0)
    clf_lm_xgb, pred_valid_lm_xgb, pred_test_lm_xgb = fit_xgb(X_train_lm_raw, X_valid_lm_raw, X_test_lm_raw)
    log("=" * 60)
    log("BASELINE B2 -- SENTIMENT LEXICON (LM) + XGBOOST -> volatility_class")
    log("=" * 60)
    report_block(log, "lm_xgb", y_valid, pred_valid_lm_xgb, y_test, pred_test_lm_xgb, labels)

    joblib.dump(scaler, MODEL_DIR / "lm_scaler.pkl")
    joblib.dump(clf_lm_lr, MODEL_DIR / "lm_logreg.pkl")
    joblib.dump(clf_lm_xgb, MODEL_DIR / "lm_xgb.pkl")
    log(f"Tersimpan: {MODEL_DIR / 'lm_scaler.pkl'}, lm_logreg.pkl, lm_xgb.pkl")
    log()

    # =========================================================================
    log("=" * 60)
    log("PERBANDINGAN AKURASI TEST (target: volatility_class)")
    log("=" * 60)
    log(f"  Dummy (kelas mayoritas)         : {dummy_acc_test:.3f}")
    log(f"  Naive persistence (acuan harga) : {naive_acc_test:.3f}")
    log(f"  TF-IDF + Logistic Regression    : {accuracy_score(y_test, pred_test_tfidf_lr):.3f}")
    log(f"  TF-IDF + XGBoost                : {accuracy_score(y_test, pred_test_tfidf_xgb):.3f}")
    log(f"  LM     + Logistic Regression    : {accuracy_score(y_test, pred_test_lm_lr):.3f}")
    log(f"  LM     + XGBoost                : {accuracy_score(y_test, pred_test_lm_xgb):.3f}")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log(f"\nLaporan tersimpan: {REPORT_PATH}")


if __name__ == "__main__":
    main()
