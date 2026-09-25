"""
train_baseline_ts.py
=====================
Baseline TIME-SERIES MURNI -- prediksi volatility_class (low/medium/high)
CUMA dari histori nilai tukar (lag log_return & lag realized_vol), TANPA
teks berita sama sekali. Ini "Tahap 3": tolok ukur yang harus dikalahkan
model gabungan di train_combined.py (Tahap 4).

Split & label volatility_class dari dataset_split.py (70/15/15 kronologis,
ambang batas low/medium/high di-fit dari train saja -- lihat docstring di
sana buat alasannya).

DUA MODEL:
  1. Naive persistence : prediksi hari t = kelas volatility hari t-1
     (lag1_volatility_class). Baseline paling minimal, wajib dikalahkan.
  2. XGBoost            : lag1-3 log_return + lag1 realized_vol -> klasifikasi
     3 kelas. Dipilih (bukan ARIMA) karena nanti gampang digabung dengan
     fitur NLP di train_combined.py -- sama-sama tabel fitur numerik.

SEMUA FITUR SUDAH di-shift(1) ATAU LEBIH oleh preprocess_kurs.py -- tidak ada
fitur di sini yang mengandung informasi hari t itu sendiri (no leakage).
"""

import joblib
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

import config as C
from dataset_split import build_dataset, log_split_summary

LAG_FEATURES = [
    "lag1_log_return", "lag2_log_return", "lag3_log_return", "lag1_realized_vol",
    "lag1_volatility_class_enc",
]

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

    train, valid, test = build_dataset(required_cols=LAG_FEATURES)
    log_split_summary(log, train, valid, test)

    labels = sorted(train["volatility_class"].unique())
    y_train, y_valid, y_test = train["volatility_class"], valid["volatility_class"], test["volatility_class"]

    dummy = DummyClassifier(strategy="most_frequent")
    dummy.fit(train[LAG_FEATURES], y_train)
    dummy_acc = accuracy_score(y_test, dummy.predict(test[LAG_FEATURES]))

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
    log(f"Akurasi dummy (kelas mayoritas, test) : {dummy_acc:.3f}")
    log(f"Akurasi naive valid                   : {acc_naive_valid:.3f}")
    log(f"Akurasi naive test                    : {acc_naive_test:.3f}")
    log()
    log("Classification report (TEST set):")
    log(classification_report(y_test, pred_test_naive, zero_division=0))
    log("Confusion matrix TEST (baris=aktual, kolom=prediksi), label urut " + str(labels))
    log(confusion_matrix(y_test, pred_test_naive, labels=labels))
    log()

    # =========================================================================
    # MODEL 2: XGBoost pakai lag log_return + lag realized_vol
    # =========================================================================
    encoder = LabelEncoder().fit(train["volatility_class"])
    y_train_enc = encoder.transform(y_train)

    clf_xgb = XGBClassifier(
        n_estimators=200, max_depth=3, learning_rate=0.05,
        eval_metric="mlogloss", random_state=42,
    )
    clf_xgb.fit(train[LAG_FEATURES], y_train_enc)
    pred_valid_xgb = encoder.inverse_transform(clf_xgb.predict(valid[LAG_FEATURES]))
    pred_test_xgb = encoder.inverse_transform(clf_xgb.predict(test[LAG_FEATURES]))
    acc_xgb_valid = accuracy_score(y_valid, pred_valid_xgb)
    acc_xgb_test = accuracy_score(y_test, pred_test_xgb)

    log("=" * 60)
    log("MODEL 2 -- XGBOOST (lag1-3 log_return + lag1 realized_vol)")
    log("=" * 60)
    log(f"Fitur dipakai: {LAG_FEATURES}")
    log(f"Akurasi dummy (kelas mayoritas, test) : {dummy_acc:.3f}")
    log(f"Akurasi XGBoost valid                 : {acc_xgb_valid:.3f}")
    log(f"Akurasi XGBoost test                  : {acc_xgb_test:.3f}")
    log()
    log("Classification report (TEST set):")
    log(classification_report(y_test, pred_test_xgb, zero_division=0))
    log("Confusion matrix TEST (baris=aktual, kolom=prediksi), label urut " + str(labels))
    log(confusion_matrix(y_test, pred_test_xgb, labels=labels))
    log()
    log("Feature importance:")
    for f, imp in sorted(zip(LAG_FEATURES, clf_xgb.feature_importances_), key=lambda x: -x[1]):
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
    log(f"  Dummy (kelas mayoritas) : {dummy_acc:.3f}")
    log(f"  Naive persistence       : {acc_naive_test:.3f}")
    log(f"  XGBoost (lag price)     : {acc_xgb_test:.3f}")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log(f"\nLaporan tersimpan: {REPORT_PATH}")


if __name__ == "__main__":
    main()
