"""
train_baseline_ts.py
=====================
Baseline TIME-SERIES MURNI -- prediksi volatility_class (low/medium/high)
CUMA dari histori nilai tukar (PRICE_FEATURES di dataset_split.py), TANPA
teks berita sama sekali. Ini "Tahap 3": tolok ukur yang harus dikalahkan
model gabungan di train_combined.py (Tahap 4).

Split & label volatility_class dari dataset_split.py (70/15/15 kronologis,
ambang batas low/medium/high di-fit dari train saja -- lihat docstring di
sana buat alasannya).

DUA MODEL:
  1. Naive persistence : prediksi hari t = kelas volatility hari t-1
     (lag1_volatility_class). Baseline paling minimal, wajib dikalahkan.
  2. XGBoost            : PRICE_FEATURES -> klasifikasi 3 kelas, hyperparameter
     di-tuning via akurasi VALID (grid yang sama dgn train_combined.py). Dipilih (bukan ARIMA) karena nanti gampang digabung dengan
     fitur NLP di train_combined.py -- sama-sama tabel fitur numerik.

SEMUA FITUR SUDAH di-shift(1) ATAU LEBIH (preprocess_kurs.py / dataset_split.py) -- tidak ada
fitur di sini yang mengandung informasi hari t itu sendiri (no leakage).
"""

import joblib
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.preprocessing import LabelEncoder

import config as C
from dataset_split import PRICE_FEATURES, build_dataset, log_split_summary, tune_xgb

LOG_DIR = C.ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = LOG_DIR / "train_baseline_ts_report.txt"

MODEL_DIR = C.ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def main():
    lines = []

    def log(msg=""):
        print(msg)
        lines.append(str(msg))

    train, valid, test = build_dataset(required_cols=PRICE_FEATURES)
    log_split_summary(log, train, valid, test)

    labels = sorted(train["volatility_class"].unique())
    y_train, y_valid, y_test = train["volatility_class"], valid["volatility_class"], test["volatility_class"]

    # =========================================================================
    # MODEL 1: Naive persistence
    # =========================================================================
    pred_valid_naive = valid["lag1_volatility_class"]
    pred_test_naive = test["lag1_volatility_class"]
    acc_naive_valid = accuracy_score(y_valid, pred_valid_naive)
    acc_naive_test = accuracy_score(y_test, pred_test_naive)

    log("=" * 60)
    log("MODEL 1 -- NAIVE PERSISTENCE (volatility hari t = volatility hari t-1)")
    log("=" * 60)
    log(f"Akurasi naive valid                   : {acc_naive_valid:.3f}")
    log(f"Akurasi naive test                    : {acc_naive_test:.3f}")
    log()
    log("Classification report (TEST set):")
    log(classification_report(y_test, pred_test_naive, zero_division=0))
    log("Confusion matrix TEST (baris=aktual, kolom=prediksi), label urut " + str(labels))
    log(confusion_matrix(y_test, pred_test_naive, labels=labels))
    log()

    # =========================================================================
    # MODEL 2: XGBoost tanpa NLP (fitur harga saja), di-tuning via VALID
    # =========================================================================
    encoder = LabelEncoder().fit(train["volatility_class"])
    y_train_enc = encoder.transform(y_train)

    log("=" * 60)
    log("MODEL 2 -- XGBOOST TANPA NLP (fitur harga saja)")
    log("=" * 60)
    log(f"Fitur dipakai: {PRICE_FEATURES}")
    clf_xgb, pred_valid_xgb, pred_test_xgb = tune_xgb(
        train[PRICE_FEATURES], y_train_enc, valid[PRICE_FEATURES], y_valid,
        test[PRICE_FEATURES], encoder, log,
    )
    acc_xgb_valid = accuracy_score(y_valid, pred_valid_xgb)
    acc_xgb_test = accuracy_score(y_test, pred_test_xgb)
    log(f"Akurasi XGBoost valid                 : {acc_xgb_valid:.3f}")
    log(f"Akurasi XGBoost test                  : {acc_xgb_test:.3f}")
    log()
    log("Classification report (TEST set):")
    log(classification_report(y_test, pred_test_xgb, zero_division=0))
    log("Confusion matrix TEST (baris=aktual, kolom=prediksi), label urut " + str(labels))
    log(confusion_matrix(y_test, pred_test_xgb, labels=labels))
    log()
    log("Feature importance:")
    for f, imp in sorted(zip(PRICE_FEATURES, clf_xgb.feature_importances_), key=lambda x: -x[1]):
        log(f"  {f}: {imp:.3f}")
    log()

    joblib.dump(clf_xgb, MODEL_DIR / "baseline_ts_xgb.pkl")
    joblib.dump(encoder, MODEL_DIR / "baseline_ts_label_encoder.pkl")
    log(f"Tersimpan: {MODEL_DIR / 'baseline_ts_xgb.pkl'}")
    log(f"Tersimpan: {MODEL_DIR / 'baseline_ts_label_encoder.pkl'}")
    log()

    # =========================================================================
    log("=" * 60)
    log("PERBANDINGAN AKURASI TEST (target: volatility_class, tanpa fitur teks)")
    log("=" * 60)
    log(f"  Naive persistence       : {acc_naive_test:.3f}")
    log(f"  XGBoost tanpa NLP       : {acc_xgb_test:.3f}")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log(f"\nLaporan tersimpan: {REPORT_PATH}")


if __name__ == "__main__":
    main()
