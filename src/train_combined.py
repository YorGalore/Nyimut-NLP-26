"""
train_combined.py
==================
MODEL GABUNGAN -- satu XGBoost yang makan SEMUA fitur sekaligus: harga
historis (lag log_return, lag realized_vol) + TF-IDF (dikompres) + Loughran-
McDonald sentiment. Ini produk akhirnya -- bukan perbandingan "pilih salah
satu", tapi integrasi ketiganya jadi satu prediktor volatility_class.

Model-model sebelumnya (harga-saja, harga+LM tanpa TF-IDF) tetap dilaporkan
di sini sebagai TAHAPAN, supaya kelihatan kontribusi tiap fitur ditambahkan
satu-satu -- bukan buat "milih pemenang", tapi buat cek apakah tiap
penambahan fitur beneran nolong atau nggak.

KENAPA TF-IDF DIKOMPRES (TruncatedSVD) SEBELUM DIGABUNG:
--------------------------------------------------------------------------
TF-IDF menghasilkan 5.000 kolom (satu per kata/frasa), sedangkan fitur
harga+LM cuma 7 kolom. Kalau digabung mentah-mentah, split tree XGBoost
nyaris selalu jatuh ke salah satu dari 5.000 kolom TF-IDF (probabilitas
menang cuma dari jumlah kolom), dan 7 kolom harga+LM nyaris gak pernah
kepakai walau sinyalnya kuat. TruncatedSVD meringkas 5.000 kolom TF-IDF
jadi N_SVD_COMPONENTS "sumbu topik" utama (kombinasi linear kata-kata yang
sering muncul bareng) -- masih representasi TF-IDF, cuma diringkas supaya
adil headcount-nya lawan fitur harga+LM.

TF-IDF & SVD DI-FIT DI TRAIN SAJA (pola yang sama kayak train_tfidf.py):
fit_transform() di train, transform() doang di valid/test.
"""

import joblib
from sklearn.decomposition import TruncatedSVD
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier
import numpy as np
import pandas as pd

import config as C
from dataset_split import build_dataset, log_split_summary

PRICE_FEATURES = [
    "lag1_log_return", "lag2_log_return", "lag3_log_return", "lag1_realized_vol",
    "lag1_volatility_class_enc",
]
LM_FEATURES = ["mean_lm_polarity", "lm_positive_sum", "lm_negative_sum"]

# grid kecil buat tuning -- dipilih berdasarkan akurasi VALID, dites ke test
# cuma SEKALI pakai kombinasi terbaik (bukan pilih2 sambil intip test).
XGB_GRID = [
    {"n_estimators": n, "max_depth": d, "learning_rate": lr}
    for n in (100, 200, 400)
    for d in (2, 3, 4)
    for lr in (0.03, 0.05, 0.1)
]

MIN_DF = 5
MAX_DF = 0.8
NGRAM_RANGE = (1, 2)
MAX_FEATURES = 5000
N_SVD_COMPONENTS = 20

LOG_DIR = C.ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = LOG_DIR / "train_combined_report.txt"

MODEL_DIR = C.ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def fit_xgb(X_train, y_train_enc, X_valid, X_test, encoder):
    clf = XGBClassifier(
        n_estimators=200, max_depth=3, learning_rate=0.05,
        eval_metric="mlogloss", random_state=42,
    )
    clf.fit(X_train, y_train_enc)
    pred_valid = encoder.inverse_transform(clf.predict(X_valid))
    pred_test = encoder.inverse_transform(clf.predict(X_test))
    return clf, pred_valid, pred_test


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

    train, valid, test = build_dataset(required_cols=PRICE_FEATURES + LM_FEATURES)
    log_split_summary(log, train, valid, test)

    labels = sorted(train["volatility_class"].unique())
    y_train, y_valid, y_test = train["volatility_class"], valid["volatility_class"], test["volatility_class"]
    encoder = LabelEncoder().fit(y_train)
    y_train_enc = encoder.transform(y_train)

    dummy = DummyClassifier(strategy="most_frequent")
    dummy.fit(train[PRICE_FEATURES], y_train)
    dummy_acc = accuracy_score(y_test, dummy.predict(test[PRICE_FEATURES]))
    naive_acc = accuracy_score(y_test, test["lag1_volatility_class"])

    # --- fitur TF-IDF, dikompres jadi N_SVD_COMPONENTS kolom, fit di train saja
    vectorizer = TfidfVectorizer(
        min_df=MIN_DF, max_df=MAX_DF, ngram_range=NGRAM_RANGE, max_features=MAX_FEATURES,
    )
    X_train_tfidf = vectorizer.fit_transform(train["text_norm_concat"].fillna(""))
    X_valid_tfidf = vectorizer.transform(valid["text_norm_concat"].fillna(""))
    X_test_tfidf = vectorizer.transform(test["text_norm_concat"].fillna(""))

    svd = TruncatedSVD(n_components=N_SVD_COMPONENTS, random_state=42)
    Z_train = svd.fit_transform(X_train_tfidf)
    Z_valid = svd.transform(X_valid_tfidf)
    Z_test = svd.transform(X_test_tfidf)
    svd_cols = [f"tfidf_svd_{i}" for i in range(N_SVD_COMPONENTS)]
    log(f"TF-IDF vocabulary: {len(vectorizer.vocabulary_):,} kata -> dikompres jadi {N_SVD_COMPONENTS} kolom "
        f"(menjelaskan {svd.explained_variance_ratio_.sum()*100:.1f}% varians)")
    log()

    def make_X(part, Z, cols):
        price_lm = part[PRICE_FEATURES + LM_FEATURES].fillna(0).to_numpy()
        return np.hstack([price_lm, Z]), PRICE_FEATURES + LM_FEATURES + cols

    # =========================================================================
    # TAHAPAN A: harga-saja (Tahap 3, diulang di sini sebagai acuan)
    # =========================================================================
    clf_price, pred_valid_price, pred_test_price = fit_xgb(
        train[PRICE_FEATURES], y_train_enc, valid[PRICE_FEATURES], test[PRICE_FEATURES], encoder,
    )
    acc_price_test = accuracy_score(y_test, pred_test_price)

    # =========================================================================
    # TAHAPAN B: harga + LM (tanpa TF-IDF)
    # =========================================================================
    feat_b = PRICE_FEATURES + LM_FEATURES
    clf_b, pred_valid_b, pred_test_b = fit_xgb(
        train[feat_b].fillna(0), y_train_enc, valid[feat_b].fillna(0), test[feat_b].fillna(0), encoder,
    )
    acc_b_test = accuracy_score(y_test, pred_test_b)

    # =========================================================================
    # MODEL GABUNGAN AKHIR: harga + LM + TF-IDF(SVD) -- SEMUA fitur sekaligus
    # =========================================================================
    X_train_full, feat_names = make_X(train, Z_train, svd_cols)
    X_valid_full, _ = make_X(valid, Z_valid, svd_cols)
    X_test_full, _ = make_X(test, Z_test, svd_cols)

    log("=" * 60)
    log("MODEL GABUNGAN AKHIR -- harga historis + TF-IDF(SVD) + LM sentiment")
    log("=" * 60)
    log(f"Fitur dipakai ({len(feat_names)} kolom): {feat_names}")
    log()
    clf_combined, pred_valid_combined, pred_test_combined = tune_xgb(
        X_train_full, y_train_enc, X_valid_full, y_valid, X_test_full, encoder, log,
    )
    acc_combined_test = accuracy_score(y_test, pred_test_combined)
    log()
    report_block(log, y_valid, pred_valid_combined, y_test, pred_test_combined, labels)

    log("Feature importance (top 10):")
    importances = sorted(zip(feat_names, clf_combined.feature_importances_), key=lambda x: -x[1])
    for f, imp in importances[:10]:
        tag = "harga" if f in PRICE_FEATURES else ("LM" if f in LM_FEATURES else "TF-IDF")
        log(f"  [{tag}] {f}: {imp:.3f}")
    log(f"  ... total importance TF-IDF(SVD) : {sum(i for f, i in importances if f in svd_cols):.3f}")
    log(f"  ... total importance harga        : {sum(i for f, i in importances if f in PRICE_FEATURES):.3f}")
    log(f"  ... total importance LM           : {sum(i for f, i in importances if f in LM_FEATURES):.3f}")
    log()

    joblib.dump(vectorizer, MODEL_DIR / "combined_tfidf_vectorizer.pkl")
    joblib.dump(svd, MODEL_DIR / "combined_tfidf_svd.pkl")
    joblib.dump(clf_combined, MODEL_DIR / "combined_xgb.pkl")
    joblib.dump(encoder, MODEL_DIR / "combined_label_encoder.pkl")
    log(f"Tersimpan: combined_tfidf_vectorizer.pkl, combined_tfidf_svd.pkl, combined_xgb.pkl, combined_label_encoder.pkl")
    log()

    # =========================================================================
    log("=" * 60)
    log("PERBANDINGAN AKURASI TEST (target: volatility_class) -- efek menambah fitur satu-satu")
    log("=" * 60)
    log(f"  Dummy (kelas mayoritas)                        : {dummy_acc:.3f}")
    log(f"  Naive persistence                              : {naive_acc:.3f}")
    log(f"  1. Harga-saja                                  : {acc_price_test:.3f}")
    log(f"  2. Harga + LM                                  : {acc_b_test:.3f}   (selisih vs (1): {acc_b_test-acc_price_test:+.3f})")
    log(f"  3. Harga + LM + TF-IDF(SVD) -- MODEL GABUNGAN  : {acc_combined_test:.3f}   (selisih vs (2): {acc_combined_test-acc_b_test:+.3f})")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log(f"\nLaporan tersimpan: {REPORT_PATH}")


if __name__ == "__main__":
    main()
