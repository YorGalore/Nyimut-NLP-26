"""
train_tfidf.py
===============
XGBoost TEKS SAJA -- dua jalur fitur NLP -> volatility_class (low/medium/high),
TANPA fitur harga sama sekali, dievaluasi pakai split kronologis 70/15/15
dari dataset_split.py:
  MODEL A -- TF-IDF (text_norm_concat) + XGBoost
  MODEL B -- Sentiment Lexicon Loughran-McDonald (mean_lm_polarity, dst) + XGBoost

Gunanya: menguji apakah berita SENDIRIAN bisa memprediksi volatility_class.
Dibandingkan dengan XGBoost tanpa NLP (train_baseline_ts.py) dan XGBoost +
TF-IDF + LM (train_combined.py), ini menunjukkan apakah berita berguna
berdiri sendiri atau hanya sebagai TAMBAHAN di atas histori harga. Naive
persistence dilaporkan juga sebagai acuan universal yang sama.

Hari yang dipakai SAMA PERSIS dengan train_combined.py (required_cols sama),
dan XGBoost di-tuning pakai grid yang sama (tune_xgb di dataset_split.py).

TF-IDF DI-FIT DI TRAIN SAJA:
TfidfVectorizer.fit_transform() cuma dipanggil di train -- valid & test
cuma di-.transform() pakai vocabulary yang sudah dipelajari. Kalau di-fit
dari seluruh data, model "mengintip" kosakata dari peristiwa masa depan
(mis. kata yang cuma muncul di 2026) buat memprediksi masa lalu.
"""

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.preprocessing import LabelEncoder

import config as C
from dataset_split import LM_FEATURES, PRICE_FEATURES, build_dataset, log_split_summary, tune_xgb

MIN_DF = 5
MAX_DF = 0.8
NGRAM_RANGE = (1, 2)
MAX_FEATURES = 5000

LOG_DIR = C.ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = LOG_DIR / "train_tfidf_report.txt"

MODEL_DIR = C.ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def report_block(log, y_valid, pred_valid, y_test, pred_test, labels):
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

    # required_cols sama dengan train_combined.py -> himpunan hari identik
    train, valid, test = build_dataset(required_cols=PRICE_FEATURES + LM_FEATURES)
    log_split_summary(log, train, valid, test)

    labels = sorted(train["volatility_class"].unique())
    y_train, y_valid, y_test = train["volatility_class"], valid["volatility_class"], test["volatility_class"]
    encoder = LabelEncoder().fit(y_train)
    y_train_enc = encoder.transform(y_train)

    # acuan universal: sama dipakai train_baseline_ts.py & train_combined.py
    naive_acc_test = accuracy_score(y_test, test["lag1_volatility_class"])

    # =========================================================================
    # MODEL A: TF-IDF + XGBoost
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

    log("=" * 60)
    log("MODEL A -- TF-IDF + XGBOOST (teks saja) -> volatility_class")
    log("=" * 60)
    clf_tfidf_xgb, pred_valid_tfidf_xgb, pred_test_tfidf_xgb = tune_xgb(
        X_train_tfidf, y_train_enc, X_valid_tfidf, y_valid, X_test_tfidf, encoder, log,
    )
    report_block(log, y_valid, pred_valid_tfidf_xgb, y_test, pred_test_tfidf_xgb, labels)

    feature_names = np.array(vectorizer.get_feature_names_out())
    top_idx = np.argsort(clf_tfidf_xgb.feature_importances_)[-20:][::-1]
    log("Term TF-IDF paling berpengaruh (feature importance XGBoost):")
    log("  " + ", ".join(feature_names[top_idx]))
    log()

    joblib.dump(vectorizer, MODEL_DIR / "tfidf_vectorizer.pkl")
    joblib.dump(clf_tfidf_xgb, MODEL_DIR / "tfidf_xgb.pkl")
    log(f"Tersimpan: {MODEL_DIR / 'tfidf_vectorizer.pkl'}, tfidf_xgb.pkl")
    log()

    # =========================================================================
    # MODEL B: Sentiment Lexicon (Loughran-McDonald) + XGBoost
    # =========================================================================
    # XGBoost berbasis pohon -- gak butuh scaling, pakai nilai mentah
    X_train_lm = train[LM_FEATURES].fillna(0)
    X_valid_lm = valid[LM_FEATURES].fillna(0)
    X_test_lm = test[LM_FEATURES].fillna(0)
    log("=" * 60)
    log("MODEL B -- SENTIMENT LEXICON (LM) + XGBOOST (teks saja) -> volatility_class")
    log("=" * 60)
    log(f"Fitur dipakai: {LM_FEATURES}")
    clf_lm_xgb, pred_valid_lm_xgb, pred_test_lm_xgb = tune_xgb(
        X_train_lm, y_train_enc, X_valid_lm, y_valid, X_test_lm, encoder, log,
    )
    report_block(log, y_valid, pred_valid_lm_xgb, y_test, pred_test_lm_xgb, labels)

    joblib.dump(clf_lm_xgb, MODEL_DIR / "lm_xgb.pkl")
    log(f"Tersimpan: {MODEL_DIR / 'lm_xgb.pkl'}")
    log()

    # =========================================================================
    log("=" * 60)
    log("PERBANDINGAN AKURASI TEST (target: volatility_class, teks saja)")
    log("=" * 60)
    log(f"  Naive persistence (acuan harga) : {naive_acc_test:.3f}")
    log(f"  TF-IDF + XGBoost                : {accuracy_score(y_test, pred_test_tfidf_xgb):.3f}")
    log(f"  LM     + XGBoost                : {accuracy_score(y_test, pred_test_lm_xgb):.3f}")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log(f"\nLaporan tersimpan: {REPORT_PATH}")


if __name__ == "__main__":
    main()
