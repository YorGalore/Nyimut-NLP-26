"""
train_combined.py
==================
MODEL GABUNGAN -- satu XGBoost yang makan SEMUA fitur sekaligus: harga
historis (PRICE_FEATURES di dataset_split.py) + TF-IDF (dikompres) + Loughran-
McDonald sentiment. Ini produk akhirnya -- bukan perbandingan "pilih salah
satu", tapi integrasi ketiganya jadi satu prediktor volatility_class.

Perbandingan utama: (1) naive persistence, (2) XGBoost tanpa NLP (harga
saja), (3) XGBoost + TF-IDF + LM. Selisih (3) vs (2) = kontribusi berita.
Semua XGBoost di-tuning pakai grid yang sama (XGB_GRID di dataset_split.py)
supaya adil. Harga + LM tanpa TF-IDF tetap dilaporkan sebagai ablasi.

KENAPA TF-IDF DIKOMPRES (TruncatedSVD) SEBELUM DIGABUNG:
--------------------------------------------------------------------------
TF-IDF menghasilkan 5.000 kolom (satu per kata/frasa), sedangkan fitur
harga+LM cuma belasan kolom. Kalau digabung mentah-mentah, split tree XGBoost
nyaris selalu jatuh ke salah satu dari 5.000 kolom TF-IDF (probabilitas
menang cuma dari jumlah kolom), dan kolom harga+LM nyaris gak pernah
kepakai walau sinyalnya kuat. TruncatedSVD meringkas 5.000 kolom TF-IDF
jadi N_SVD_COMPONENTS "sumbu topik" utama (kombinasi linear kata-kata yang
sering muncul bareng) -- masih representasi TF-IDF, cuma diringkas supaya
adil headcount-nya lawan fitur harga+LM.

TF-IDF & SVD DI-FIT DI TRAIN SAJA (pola yang sama kayak train_tfidf.py):
fit_transform() di train, transform() doang di valid/test.
"""

import joblib
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.preprocessing import LabelEncoder
import numpy as np
from scipy.stats import binomtest

import config as C
from dataset_split import LM_FEATURES, PRICE_FEATURES, build_dataset, log_split_summary, tune_xgb

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


def mcnemar(y_true, pred_a, pred_b):
    """
    Uji McNemar exact: apakah model A dan B beda akurasi secara signifikan di
    hari-hari yang SAMA. Cuma hari yang hasilnya BEDA (A benar & B salah, atau
    sebaliknya) yang dihitung; di bawah H0 keduanya sama mungkin (binomial p=0,5).
    """
    y_true, pred_a, pred_b = map(np.asarray, (y_true, pred_a, pred_b))
    a_only = int(((pred_a == y_true) & (pred_b != y_true)).sum())
    b_only = int(((pred_a != y_true) & (pred_b == y_true)).sum())
    p = binomtest(a_only, a_only + b_only).pvalue if a_only + b_only else 1.0
    return a_only, b_only, p


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
    # TAHAPAN A: XGBoost tanpa NLP (harga saja; sama dengan train_baseline_ts.py)
    # =========================================================================
    log("=" * 60)
    log("XGBOOST TANPA NLP -- harga historis saja")
    log("=" * 60)
    clf_price, pred_valid_price, pred_test_price = tune_xgb(
        train[PRICE_FEATURES], y_train_enc, valid[PRICE_FEATURES], y_valid,
        test[PRICE_FEATURES], encoder, log,
    )
    log()
    acc_price_test = accuracy_score(y_test, pred_test_price)

    # =========================================================================
    # TAHAPAN B (ablasi): harga + LM (tanpa TF-IDF)
    # =========================================================================
    feat_b = PRICE_FEATURES + LM_FEATURES
    log("=" * 60)
    log("ABLASI -- harga + LM (tanpa TF-IDF)")
    log("=" * 60)
    clf_b, pred_valid_b, pred_test_b = tune_xgb(
        train[feat_b].fillna(0), y_train_enc, valid[feat_b].fillna(0), y_valid,
        test[feat_b].fillna(0), encoder, log,
    )
    log()
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
    log("PERBANDINGAN AKURASI TEST (target: volatility_class)")
    log("=" * 60)
    log(f"  1. Naive persistence (baseline)                : {naive_acc:.3f}")
    log(f"  2. XGBoost tanpa NLP (harga saja)              : {acc_price_test:.3f}   (selisih vs (1): {acc_price_test-naive_acc:+.3f})")
    log(f"  3. XGBoost + TF-IDF + LM -- MODEL UTAMA        : {acc_combined_test:.3f}   (selisih vs (2): {acc_combined_test-acc_price_test:+.3f})")
    log()
    log(f"  Ablasi: XGBoost harga + LM (tanpa TF-IDF)      : {acc_b_test:.3f}   (selisih vs (2): {acc_b_test-acc_price_test:+.3f})")
    log()
    log("Uji signifikansi McNemar (TEST, alpha=0,05) -- 'A saja benar / B saja benar':")
    naive_pred = test["lag1_volatility_class"].astype(str)
    for name, pa, pb in (
        ("(2) vs (1) naive      ", pred_test_price, naive_pred),
        ("(3) vs (2) tanpa NLP  ", pred_test_combined, pred_test_price),
        ("(3) vs (1) naive      ", pred_test_combined, naive_pred),
    ):
        a_only, b_only, p = mcnemar(y_test, pa, pb)
        log(f"  {name}: {a_only:>3} / {b_only:<3} hari  p = {p:.3f}  {'SIGNIFIKAN' if p < 0.05 else 'tidak signifikan'}")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log(f"\nLaporan tersimpan: {REPORT_PATH}")


if __name__ == "__main__":
    main()
