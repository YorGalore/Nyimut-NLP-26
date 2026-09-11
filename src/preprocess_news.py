"""
preprocess_news.py
==================
Pipeline pembersihan teks berita: data/raw/cnbc_raw.csv -> data/processed/news_clean.csv

URUTAN TAHAP (urutannya disengaja, bukan acak):

  1. Deduplikasi struktural   -- paling murah, dilakukan duluan supaya tahap
                                 berikutnya memproses lebih sedikit baris
  2. Buang tipe non-artikel   -- video, slideshow, halaman kuotasi saham
  3. Normalisasi Unicode/HTML -- unescape entitas, NFKC, buang zero-width char
  4. Buang boilerplate CNBC   -- kalimat berulang yang muncul di ribuan artikel
  5. Filter panjang           -- dokumen terlalu pendek tidak informatif
  6. Filter relevansi tahap-2 -- skoring leksikon berbobot + leksikon negatif
  7. Dua jalur output teks    -- text_clean (untuk transformer)
                                 text_norm  (untuk baseline TF-IDF)

KEPUTUSAN PENTING: DUA JALUR TEKS
---------------------------------
Kami sengaja TIDAK menghasilkan satu kolom teks.

  text_clean : kapitalisasi asli, tanda baca utuh, angka utuh.
               Dipakai untuk BERT/FinBERT dan NER. Model transformer punya
               tokenizer sendiri dan MEMBUTUHKAN kapitalisasi -- pada korpus
               ini itu krusial untuk membedakan "US" (negara) dari "us"
               (kata ganti). Tanda baca menandai batas kalimat.

  text_norm  : lowercase, tanda baca dibuang, stopword dibuang.
               Dipakai untuk baseline bag-of-words / TF-IDF.

Menyediakan keduanya berarti Tugas 2 dan 3 tidak perlu scraping ulang.

YANG SENGAJA TIDAK DIBUANG (kebalikan dari pipeline default):
  - Angka & persentase  : "oil surges 8%", "sanksi $100 miliar" -- magnitudo
                          adalah sinyal, bukan noise.
  - Kata negasi         : not / no / never / without. Daftar stopword standar
                          membuang ini dan MEMBALIK makna sentimen.
  - Nama entitas        : Russia, OPEC, Iran -- ini prediktor utamanya.
  - Stemming agresif    : dilewati. Pada korpus penuh nama diri, stemming
                          lebih sering merusak ("Chinese" -> "chines")
                          daripada membantu.
"""

import html
import re
import unicodedata

import pandas as pd

import config as C


# ---------------------------------------------------------------------------
# Regex dikompilasi sekali di awal (dipakai puluhan ribu kali)
# ---------------------------------------------------------------------------
RE_TAG = re.compile(r"<[^>]+>")
RE_URL = re.compile(r"https?://\S+|www\.\S+")
RE_WS = re.compile(r"\s+")
RE_ZEROWIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")
RE_BOILER = [re.compile(p, re.IGNORECASE) for p in C.BOILERPLATE_PATTERNS]
RE_TITLE_NORM = re.compile(r"[^a-z0-9 ]")
RE_TOKEN = re.compile(r"[a-z0-9%$][a-z0-9%$'\-\.]*")

# Leksikon relevansi -> regex dengan word boundary, supaya "war" tidak
# ikut cocok di dalam kata "warehouse" atau "reward".
LEX_PATTERNS = {
    term: re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
    for term in C.GEO_LEXICON
}
NEG_PATTERNS = [re.compile(re.escape(t), re.IGNORECASE) for t in C.NEGATIVE_LEXICON]


# ---------------------------------------------------------------------------
# TAHAP 3 & 4 -- pembersihan karakter dan boilerplate
# ---------------------------------------------------------------------------
def clean_text(text):
    """
    Menghasilkan text_clean: teks yang sudah bersih TAPI masih natural.
    Kapitalisasi dan tanda baca dipertahankan.
    """
    if not isinstance(text, str):
        return ""

    # Unescape entitas HTML dua kali: sebagian feed melakukan double-encoding
    # sehingga "&amp;amp;" perlu dua putaran untuk jadi "&".
    t = html.unescape(html.unescape(text))

    t = RE_TAG.sub(" ", t)          # sisa tag HTML
    t = RE_URL.sub(" ", t)          # URL tidak membawa makna semantik
    t = RE_ZEROWIDTH.sub("", t)     # zero-width & directional marks

    # NFKC menyatukan varian karakter: non-breaking space -> spasi biasa,
    # ligatur -> huruf terpisah, angka lebar-penuh -> angka biasa.
    t = unicodedata.normalize("NFKC", t)

    # CATATAN: NFKC TIDAK menormalkan tanda kutip melengkung (smart quotes).
    # Ini ketahuan saat pengujian: "don't" dengan U+2019 tetap utuh setelah
    # NFKC, lalu tokenizer memotongnya jadi "don" saja. Jadi harus dipetakan
    # manual. Tanpa ini, "don't" dan "don't" dihitung sebagai dua kata berbeda
    # dan sebagian kontraksi kehilangan ekornya.
    for src, dst in {
        "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
        "\u201c": '"', "\u201d": '"', "\u201e": '"',
        "\u2013": "-", "\u2014": "-", "\u2212": "-",
        "\u2026": "...", "\u00a0": " ",
    }.items():
        t = t.replace(src, dst)

    for pat in RE_BOILER:           # tahap 4
        t = pat.sub(" ", t)

    t = RE_WS.sub(" ", t).strip()
    return t


def normalize_text(text):
    """
    Menghasilkan text_norm untuk baseline bag-of-words.
    Lowercase + tokenisasi + buang stopword.

    Perhatikan pola RE_TOKEN: ia sengaja mengizinkan $ dan % agar token
    seperti "8%" dan "$100" tetap utuh -- itu informasi magnitudo.
    """
    if not text:
        return ""
    tokens = RE_TOKEN.findall(text.lower())
    tokens = [tok.strip(".-'") for tok in tokens]
    tokens = [tok for tok in tokens if tok and tok not in C.STOPWORDS and len(tok) > 1]
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# TAHAP 6 -- skoring relevansi
# ---------------------------------------------------------------------------
def relevance_score(text):
    """
    Skor = jumlah bobot istilah leksikon yang muncul (dihitung sekali per
    istilah, bukan per kemunculan -- supaya artikel panjang tidak otomatis
    menang hanya karena mengulang satu kata).

    Mengembalikan (skor, daftar istilah yang cocok) supaya keputusan filter
    bisa diaudit -- bukan kotak hitam.
    """
    score, matched = 0, []
    for term, weight in C.GEO_LEXICON.items():
        if LEX_PATTERNS[term].search(text):
            score += weight
            matched.append(term)
    return score, matched


def has_negative(text):
    return any(p.search(text) for p in NEG_PATTERNS)


# ---------------------------------------------------------------------------
# PIPELINE UTAMA
# ---------------------------------------------------------------------------
def main():
    df = pd.read_csv(C.CNBC_RAW_CSV)
    log = [("0. Data mentah", len(df))]

    # --- TAHAP 1a: gabungkan jejak keyword sebelum dedup ---------------------
    # Satu artikel bisa ditemukan oleh beberapa keyword. Berapa banyak keyword
    # yang menemukannya adalah sinyal kekuatan relevansi -> simpan sebagai fitur.
    df["url"] = df["url"].astype(str).str.strip()
    kw_agg = (
        df.groupby("url")
        .agg(
            search_keywords=("search_keyword", lambda s: "|".join(sorted(set(s.dropna())))),
            keyword_groups=("keyword_group", lambda s: "|".join(sorted(set(s.dropna())))),
            n_keyword_hits=("search_keyword", lambda s: s.nunique()),
        )
        .reset_index()
    )

    # --- TAHAP 1b: dedup berdasarkan URL ------------------------------------
    df = df.drop_duplicates(subset=["url"], keep="first")
    df = df.merge(kw_agg, on="url", how="left")
    df = df.drop(columns=["search_keyword", "keyword_group"], errors="ignore")
    log.append(("1. Setelah dedup URL", len(df)))

    # --- TAHAP 1c: dedup judul ternormalisasi -------------------------------
    # CNBC kadang menerbitkan ulang artikel yang sama dengan URL berbeda.
    # Judul yang dinormalisasi (lowercase, tanpa tanda baca) menangkap kasus ini.
    df["_title_key"] = (
        df["title"].astype(str).str.lower().apply(lambda s: RE_TITLE_NORM.sub("", s).strip())
    )
    df = df.drop_duplicates(subset=["_title_key"], keep="first")
    log.append(("2. Setelah dedup judul", len(df)))

    # --- TAHAP 2: buang tipe non-artikel ------------------------------------
    type_l = df["type"].astype(str).str.lower()
    sect_l = df["section"].astype(str).str.lower()
    mask_type = type_l.isin(C.DROP_TYPES)
    mask_sect = sect_l.apply(lambda s: any(k in s for k in C.DROP_SECTION_KEYWORDS))
    df = df[~(mask_type | mask_sect)]
    log.append(("3. Setelah buang video/non-artikel", len(df)))

    # --- TAHAP 3 & 4: bersihkan teks ----------------------------------------
    # Judul + deskripsi digabung jadi satu dokumen. Judul membawa sinyal
    # terkuat, deskripsi memberi konteks. Keduanya dibersihkan terpisah lalu
    # disambung agar boilerplate di deskripsi tidak mencemari judul.
    df["title_clean"] = df["title"].apply(clean_text)
    df["desc_clean"] = df["description"].apply(clean_text)
    df["text_clean"] = (df["title_clean"] + ". " + df["desc_clean"]).str.strip(". ").str.strip()

    # --- TAHAP 5: filter panjang --------------------------------------------
    df["n_tokens"] = df["text_clean"].str.split().str.len()
    df = df[df["n_tokens"] >= C.MIN_TOKENS]
    log.append((f"4. Setelah filter panjang (>= {C.MIN_TOKENS} token)", len(df)))

    # --- TAHAP 6: relevansi --------------------------------------------------
    scored = df["text_clean"].apply(relevance_score)
    df["relevance_score"] = [s for s, _ in scored]
    df["matched_terms"] = ["|".join(m) for _, m in scored]
    df["has_negative"] = df["text_clean"].apply(has_negative)

    keep = (df["relevance_score"] >= C.RELEVANCE_THRESHOLD) & (~df["has_negative"])

    # Simpan yang DITOLAK juga. Ini bukan basa-basi: saat evaluasi kalian bisa
    # menunjukkan contoh konkret apa yang dibuang filter dan kenapa.
    df[~keep].to_csv(C.NEWS_REJECTED_CSV, index=False)
    df = df[keep]
    log.append((f"5. Setelah filter relevansi (skor >= {C.RELEVANCE_THRESHOLD})", len(df)))

    # --- TAHAP 7: jalur kedua (text_norm) -----------------------------------
    df["text_norm"] = df["text_clean"].apply(normalize_text)

    # --- waktu: simpan UTC dan WIB ------------------------------------------
    # Keduanya disimpan supaya alignment bisa diaudit ulang tanpa konversi ulang.
    df["published_utc"] = pd.to_datetime(
        df["published"], utc=True, errors="coerce", format="mixed"
    )
    df = df.dropna(subset=["published_utc"])
    df["published_wib"] = df["published_utc"].dt.tz_convert(C.TZ_MARKET)
    log.append(("6. Setelah validasi timestamp", len(df)))

    # --- kolom final ---------------------------------------------------------
    cols = [
        "article_id", "url", "title_clean", "text_clean", "text_norm",
        "section", "author", "published_utc", "published_wib",
        "search_keywords", "keyword_groups", "n_keyword_hits",
        "relevance_score", "matched_terms", "n_tokens",
    ]
    out = df[[c for c in cols if c in df.columns]].sort_values("published_utc")
    out.to_csv(C.NEWS_CLEAN_CSV, index=False)

    # --- laporan penyusutan --------------------------------------------------
    # Tabel ini langsung bisa disalin ke laporan PDF sebagai bukti pipeline.
    print("\nPENYUSUTAN DATA PER TAHAP")
    print("-" * 55)
    prev = log[0][1]
    for label, n in log:
        pct = f"{(n/prev*100 - 100):+.1f}%" if prev else ""
        print(f"  {label:<48s} {n:>7,}  {pct}")
        prev = n
    print("-" * 55)
    print(f"Tersimpan: {C.NEWS_CLEAN_CSV}")
    print(f"Ditolak  : {C.NEWS_REJECTED_CSV}")
    print(f"\nDistribusi per kelompok keyword:")
    print(out["keyword_groups"].str.split("|").explode().value_counts().to_string())


if __name__ == "__main__":
    main()