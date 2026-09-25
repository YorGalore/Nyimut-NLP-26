"""
sentiment_lexicon.py
=====================
Jalur fitur LEXICON-BASED SENTIMENT (Loughran-McDonald) -- terpisah dari
jalur TF-IDF (preprocess_news_tfidf.py), tapi start dari korpus yang SAMA
dan NULIS BALIK ke file yang sama:
data/processed/news_tfidf_clean.csv -> data/processed/news_tfidf_clean.csv (ditambah kolom lm_*)

KENAPA NULIS BALIK KE news_tfidf_clean.csv, BUKAN FILE TERPISAH:
--------------------------------------------------------------------
Mengikuti pola yang sudah dipakai align.py (yang juga menambah kolom
target_date/is_offhours ke file yang sama, bukan bikin file baru). Dengan
kolom lm_* nempel di baris artikel yang sama, align.py tinggal
mengagregasinya ke level harian persis seperti relevance_score
(mean_relevance/max_relevance) -- tidak perlu join tambahan di align.py.

URUTAN JALANKAN (WAJIB):
  1. preprocess_news_tfidf.py  (bikin news_tfidf_clean.csv + text_norm)
  2. sentiment_lexicon.py      (file ini -- nambah kolom lm_* di file yang sama)
  3. align.py                  (agregasi lm_* ke level harian -> aligned_daily.csv)
Kalau align.py dijalankan SEBELUM file ini, kolom lm_* belum ada dan
agregasinya akan error -- jalankan file ini duluan.

KENAPA CUKUP DARI text_norm, TIDAK PERLU BALIK KE cnbc_raw.csv:
--------------------------------------------------------------------
Loughran-McDonald bukan lexicon berbasis konteks/intensitas kayak VADER --
tokenizer bawaannya (di paket pysentiment2) sendiri yang lowercase, buang
non-huruf, dan stem tiap token sebelum dicocokkan ke daftar kata. Jadi
kapitalisasi/tanda baca asli tidak menambah sinyal apa pun; text_norm yang
sudah ada di news_tfidf_clean.csv sudah cukup, dan ini juga sekaligus
menjaga MASUKAN dua jalur fitur (TF-IDF dan sentiment) tetap konsisten --
sama-sama dari text_norm, dokumen yang sama.

SEMANTIK SKOR (lihat pysentiment2.base.BaseDict):
  lm_positive / lm_negative : jumlah kata match di daftar positif/negatif LM
  lm_polarity   = (pos - neg) / (pos + neg)   -> arah tone, [-1, 1]
  lm_subjectivity = (pos + neg) / n_token     -> seberapa "bermuatan" tone
                                                  teksnya (rasio kata bertone
                                                  dari total token)
"""

import pandas as pd
import pysentiment2 as ps

import config as C


def score_lm(lm, text):
    tokens = lm.tokenize(text) if isinstance(text, str) else []
    s = lm.get_score(tokens)
    return pd.Series({
        "lm_n_tokens": len(tokens),
        "lm_positive": s["Positive"],
        "lm_negative": s["Negative"],
        "lm_polarity": s["Polarity"],
        "lm_subjectivity": s["Subjectivity"],
    })


def main():
    df = pd.read_csv(C.NEWS_TFIDF_CSV)
    print(f"Artikel di korpus (news_tfidf_clean.csv): {len(df):,}")

    lm = ps.LM()
    lm_scores = df["text_norm"].apply(lambda t: score_lm(lm, t))

    df = pd.concat([df, lm_scores], axis=1)
    df.to_csv(C.NEWS_TFIDF_CSV, index=False)

    print("\nRINGKASAN SENTIMENT SCORING (Loughran-McDonald)")
    print("-" * 55)
    print(f"  Polarity  -- mean: {df['lm_polarity'].mean():+.3f}  std: {df['lm_polarity'].std():.3f}")
    print(f"  Subjectivity -- mean: {df['lm_subjectivity'].mean():.3f}")
    print(f"  Artikel tanpa kata pos/neg sama sekali: "
          f"{((df['lm_positive'] == 0) & (df['lm_negative'] == 0)).sum():,} dari {len(df):,}")
    print(f"\nKolom lm_* ditambahkan ke: {C.NEWS_TFIDF_CSV}")


if __name__ == "__main__":
    main()
