"""
preprocess_news_bert.py
========================
Pipeline pembersihan teks khusus untuk model berbasis BERT (mis. FinBERT).

BEDA DENGAN preprocess_news.py:
  - Sumber teks: kolom `body` di data/raw/cnbc_raw.csv (artikel LENGKAP hasil
    scraping HTML / "Stage 3"), bukan `description` yang terpotong ~2000 char.
  - Cleaning MINIMAL: BERT punya tokenizer sendiri dan butuh teks senatural
    mungkin. Yang dibuang HANYA noise struktural (tag HTML, URL, boilerplate
    CNBC) -- BUKAN stopword, BUKAN tanda baca, BUKAN stemming, BUKAN lowercase.
  - $, %, koma, titik (baik penutup kalimat maupun desimal) WAJIB dipertahankan
    karena itu sinyal magnitudo yang penting untuk analisis dampak ke kurs.

File ini TIDAK membaca/menulis apa pun secara otomatis saat di-import --
hanya berisi fungsi cleaning + self_check(). Pipeline penuh menyusul di
langkah berikutnya setelah cleaning-nya disetujui.
"""

import html
import re
import unicodedata

import pandas as pd


# ---------------------------------------------------------------------------
# Normalisasi karakter "keriting" -> versi standar (sama seperti
# preprocess_news.py, supaya konsisten di seluruh proyek)
# ---------------------------------------------------------------------------
CURLY_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-",
    "…": "...", " ": " ",
}

RE_TAG = re.compile(r"<[^>]+>")
RE_URL = re.compile(r"https?://\S+|www\.\S+")
RE_WS = re.compile(r"\s+")
RE_ZEROWIDTH = re.compile(r"[​-‏‪-‮﻿]")

# Hanya dihapus kalau ada PERSIS di awal body -- ini label widget saham yang
# ikut ter-scrape ("In this article XOM -1.2% ..."), bukan bagian kalimat.
# Ditemukan di 1.534/1.535 kemunculan "in this article" pada corpus body;
# 1 sisanya muncul di tengah kalimat asli dan harus tetap utuh, makanya
# tidak dibuat jadi pola umum di tengah teks.
RE_LEADING_WIDGET = re.compile(r"^\s*In this article\s*", re.IGNORECASE)

# Footer panjang segmen Mad Money/Jim Cramer selalu muncul di AKHIR artikel
# (Disclaimer, nomor telepon, akun sosial media) -- dihapus dari titik itu
# sampai akhir teks, bukan cuma satu kalimat.
RE_TRAILING_CRAMER = re.compile(
    r"Click here to read Jim Cramer's Guide to Investing.*$",
    re.IGNORECASE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# "Akhir kalimat yang aman": [^.]*\. polos berhenti tepat di tengah singkatan
# seperti "U.S." / "U.K." (dibuktikan lewat pengujian di body asli -- lihat
# docs/keputusan.md). Ini corpus geopolitik, jadi U.S./U.K./U.N./E.U. muncul
# di HAMPIR SETIAP artikel. SENT_END memperlakukan 4 singkatan itu sebagai
# satu token utuh supaya titik di dalamnya tidak dianggap akhir kalimat.
# ---------------------------------------------------------------------------
SENT_END = r"(?:U\.S\.|U\.K\.|U\.N\.|E\.U\.|[^.])*\."

# Boilerplate level-kalimat: dihapus hanya kalimat yang cocok, sisanya utuh.
# Setiap pola di bawah SUDAH DIVERIFIKASI ke seluruh corpus body (6.770 baris)
# -- bukan hanya diuji di contoh kecil -- supaya tidak ada kalimat asli yang
# ikut terpotong (lihat catatan di bawah untuk pola yang SENGAJA tidak dipakai).
BOILERPLATE_PATTERNS = [
    r"Sign up (for|now)" + SENT_END,                       # 0/176 rusak di body
    r"Subscribe to CNBC on YouTube\.",                      # bentuk tetap, 39x
    r"Subscribe to CNBC PRO for exclusive insights and analysis, "
    r"and live business day programming from around the world\.",  # bentuk tetap, 18x
    r"[—\-]\s*CNBC'?s [^.]*contributed to this (report|story)\.",  # selalu diakhiri kata tetap
    r"Correction:\s*This (story|article)" + SENT_END,       # diperbaiki dgn SENT_END
    r"Disclosure:" + SENT_END,                              # 0/50 rusak di body
    r"This is breaking news\.?\s*(Please )?check back for updates\.?",
    # Kalimat pembuka template kolom "CNBC Daily Open" -- identik di 26/6.770
    # artikel (bukan iklan, tapi framing berulang tanpa sinyal unik).
    r"This report is from today'?s CNBC Daily Open[^.]*\.\s*"
    r"CNBC Daily Open brings investors up to speed[^.]*\.\s*"
    r"Like what you see\?\s*You can subscribe here\s*\.",
]
RE_BOILER = [re.compile(p, re.IGNORECASE) for p in BOILERPLATE_PATTERNS]

# SENGAJA TIDAK dijadikan pola auto-strip meski terlihat seperti boilerplate:
# "Don't miss ...", "Read more: ...", "Follow CNBC ..." (bentuk umum).
# Di kolom `body`, ketiganya adalah judul tautan yang nempel LANGSUNG ke
# paragraf berikutnya tanpa titik pemisah -- diuji ke corpus asli, regex
# manapun yang mencari "titik berikutnya" akan ikut memakan kalimat ASLI yang
# tidak berkaitan (terbukti: satu artikel kehilangan kalimat soal CPI-W/Social
# Security gara-gara dianggap sambungan "Don't miss ..."). Lebih aman
# membiarkan noise ini di teks daripada berisiko memotong konten asli.


def clean_text(text):
    """
    Bersihkan satu teks artikel untuk BERT: hapus noise struktural,
    pertahankan kapitalisasi, tanda baca, angka, $, dan %.
    """
    if not isinstance(text, str) or not text.strip():
        return ""

    t = html.unescape(html.unescape(text))  # dua putaran: sebagian feed double-encode

    t = RE_LEADING_WIDGET.sub("", t)        # label widget saham di awal
    t = RE_TRAILING_CRAMER.sub("", t)       # footer Mad Money di akhir

    t = RE_TAG.sub(" ", t)                  # sisa tag HTML
    t = RE_URL.sub(" ", t)                  # URL tidak membawa makna semantik
    t = RE_ZEROWIDTH.sub("", t)             # zero-width & directional marks

    t = unicodedata.normalize("NFKC", t)    # non-breaking space, ligatur, dst.

    for src, dst in CURLY_MAP.items():      # kutip/hubung keriting -> standar
        t = t.replace(src, dst)

    for pat in RE_BOILER:                   # boilerplate level-kalimat
        t = pat.sub(" ", t)

    t = RE_WS.sub(" ", t).strip()
    return t


def self_check():
    """
    Bukti bahwa cleaning tidak merusak sinyal yang harus dipertahankan:
    $ + angka, titik (kalimat & desimal), %, dan tidak menghapus konten asli
    yang kebetulan mirip pola boilerplate.
    """
    cases = [
        (
            "Oil rose to $85.40 a barrel. Stocks fell 2.3%.",
            "Oil rose to $85.40 a barrel. Stocks fell 2.3%.",
        ),
        (
            "In this article Iran-backed Houthi rebels killed six people.",
            "Iran-backed Houthi rebels killed six people.",
        ),
        (
            "...like others in this article, were granted anonymity to discuss plans.",
            "...like others in this article, were granted anonymity to discuss plans.",
        ),
        (
            "Sanctions cost Russia $100 billion, Reuters reported. Sign up for CNBC Pro Start your free trial now — CNBC's Amanda Macias contributed to this report.",
            "Sanctions cost Russia $100 billion, Reuters reported.",
        ),
        (
            "The rate hike was 0.25%. Disclosure: Cramer's Charitable Trust owns shares of Devon Energy. Click here to read Jim Cramer's Guide to Investing at no cost to help you build long-term wealth and invest smarter Sign up now for the CNBC Investing Club.",
            "The rate hike was 0.25%.",
        ),
        (
            "He said “don’t panic” — markets will recover.",
            'He said "don\'t panic" - markets will recover.',
        ),
        (
            "Biden announced another $800\xa0million in military assistance.",
            "Biden announced another $800 million in military assistance.",
        ),
        (
            "This report is from today's CNBC Daily Open, our new, international markets newsletter. "
            "CNBC Daily Open brings investors up to speed on everything they need to know, no matter where they are. "
            "Like what you see? You can subscribe here . Tepid markets rose 0.4% on Monday.",
            "Tepid markets rose 0.4% on Monday.",
        ),
        (
            # Kasus nyata dari corpus: [^.]*\. polos akan berhenti di "U." saja
            # dan menyisakan pecahan "S. Deputy..." -- SENT_END harus melewati
            # "U.S." utuh dan berhenti di titik akhir kalimat yang sebenarnya.
            "Correction: This story has been updated to remove an incorrect "
            "reference to where U.S. Deputy Treasury Secretary Wally Adeyemo "
            "was speaking. Real reporting continues here.",
            "Real reporting continues here.",
        ),
        (
            # "Don't miss ..." SENGAJA tidak dihapus -- dibiarkan utuh karena
            # tidak ada pemisah kalimat yang aman di kolom body (lihat komentar
            # di BOILERPLATE_PATTERNS).
            "Don't miss these tax strategies during the sell-off. Inflation data released Thursday shows CPI rose 2.2%.",
            "Don't miss these tax strategies during the sell-off. Inflation data released Thursday shows CPI rose 2.2%.",
        ),
    ]

    print("SELF CHECK clean_text()")
    print("-" * 70)
    all_ok = True
    for raw, expected in cases:
        got = clean_text(raw)
        ok = got.strip() == expected.strip()
        all_ok &= ok
        status = "OK  " if ok else "GAGAL"
        print(f"[{status}] input   : {raw}")
        print(f"        expected: {expected}")
        print(f"        got     : {got}")
        print()
    print("-" * 70)
    print("SEMUA LULUS" if all_ok else "ADA YANG GAGAL -- cek di atas")
    return all_ok


# ---------------------------------------------------------------------------
# PIPELINE (dipakai baik untuk uji coba sampel maupun produksi penuh)
# ---------------------------------------------------------------------------
import argparse
import math
import os

CHUNK_MAX_LEN = 512   # batas token model (termasuk [CLS]/[SEP])
CHUNK_OVERLAP = 50     # overlap antar potongan untuk strategi B (chunking)


def n_chunks_needed(n_tokens, max_len=CHUNK_MAX_LEN, overlap=CHUNK_OVERLAP):
    """
    Perkiraan jumlah potongan (chunk) yang dibutuhkan strategi B
    (chunking + overlap, embedding dirata-ratakan). Dipakai untuk
    memperkirakan biaya komputasi, BUKAN untuk chunking-nya sendiri --
    chunking beneran dilakukan di tahap embedding/modeling, bukan di sini.
    """
    if n_tokens <= max_len:
        return 1
    stride = max_len - overlap
    return 1 + math.ceil((n_tokens - max_len) / stride)


def build_dataset(df, tokenizer):
    """
    df: DataFrame mentah dari cnbc_raw.csv (kolom url, title, published, body,
    description, ...). Mengembalikan (out_df, log) siap ditulis ke CSV.
    """
    log = [("0. Baris masuk", len(df))]

    df = df.copy()
    df["url"] = df["url"].astype(str).str.strip()
    df = df.drop_duplicates(subset=["url"], keep="first")
    log.append(("1. Setelah dedup url", len(df)))

    body = df["body"].fillna("")
    desc = df["description"].fillna("")
    used_fallback = body.str.len() == 0
    text_raw = body.where(~used_fallback, desc)

    df["title_clean"] = df["title"].apply(clean_text)
    df["body_clean"] = text_raw.apply(clean_text)
    df["used_description_fallback"] = used_fallback
    df["text_clean"] = (
        df["title_clean"].str.rstrip(". ") + ". " + df["body_clean"]
    ).str.strip(". ").str.strip()

    n_empty = (df["text_clean"].str.len() == 0).sum()
    df = df[df["text_clean"].str.len() > 0]
    log.append((f"2. Setelah buang teks kosong ({n_empty} kosong)", len(df)))

    df["n_tokens"] = df["text_clean"].apply(
        lambda t: len(tokenizer.encode(t, add_special_tokens=True))
    )
    df["needs_chunking"] = df["n_tokens"] > CHUNK_MAX_LEN
    df["n_chunks_est"] = df["n_tokens"].apply(n_chunks_needed)

    df["date"] = pd.to_datetime(df["published"], utc=True, errors="coerce", format="mixed")

    out_cols = [
        "url", "date", "title", "text_clean", "n_tokens",
        "needs_chunking", "n_chunks_est", "used_description_fallback", "section",
    ]
    out = df[[c for c in out_cols if c in df.columns]].sort_values("date")
    return out, log


def stratified_sample(df, n, seed=42):
    """Sampel acak terstratifikasi per tahun publikasi (proporsional)."""
    years = pd.to_datetime(df["published"], utc=True, errors="coerce", format="mixed").dt.year
    frac = n / len(df)
    sampled = (
        df.groupby(years, group_keys=False)
        .apply(lambda g: g.sample(frac=frac, random_state=seed) if len(g) > 0 else g)
    )
    return sampled


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="../data/raw/cnbc_raw.csv")
    ap.add_argument("--output", required=True)
    ap.add_argument("--model", default="ProsusAI/finbert")
    ap.add_argument("--sample", type=int, default=None, help="Ambil sampel N baris (stratifikasi per tahun) sebelum diproses")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--log-dir", default="../logs")
    args = ap.parse_args()

    if not self_check():
        raise SystemExit("self_check() gagal -- cleaning tidak aman untuk dijalankan.")

    if os.path.exists(args.output):
        raise SystemExit(
            f"STOP: {args.output} sudah ada. Tidak ditimpa -- hapus manual atau "
            f"pakai nama lain kalau memang mau menulis ulang."
        )

    from transformers import AutoTokenizer
    print(f"Load tokenizer {args.model} ...")
    tokenizer = AutoTokenizer.from_pretrained(args.model)

    df = pd.read_csv(args.input)
    if args.sample:
        df = stratified_sample(df, args.sample, seed=args.seed)
        print(f"Sampel: {len(df)} baris (target {args.sample}, stratifikasi per tahun, seed={args.seed})")

    out, log = build_dataset(df, tokenizer)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    out.to_csv(args.output, index=False)

    n_needs_chunk = int(out["needs_chunking"].sum()) if "needs_chunking" in out else 0
    n_fallback = int(out["used_description_fallback"].sum()) if "used_description_fallback" in out else 0

    report_lines = [
        f"preprocess_news_bert.py -- {pd.Timestamp.now(tz='Asia/Jakarta').isoformat()}",
        f"input        : {args.input}",
        f"output       : {args.output}",
        f"model        : {args.model}",
        f"sample       : {args.sample} (seed={args.seed})" if args.sample else "sample       : (tidak ada, proses penuh)",
        "",
        "PENYUSUTAN DATA",
        "-" * 55,
    ]
    for label, n in log:
        report_lines.append(f"  {label:<40s} {n:>7,}")
    report_lines += [
        "-" * 55,
        f"Baris keluar                 : {len(out):>7,}",
        f"  - pakai fallback description : {n_fallback:>7,} (body kosong/live blog)",
        f"  - n_tokens > 512 (perlu chunking) : {n_needs_chunk:>7,} ({n_needs_chunk/len(out):.1%})",
        f"Tersimpan: {args.output}",
    ]
    report = "\n".join(report_lines)
    print("\n" + report)

    os.makedirs(args.log_dir, exist_ok=True)
    log_path = os.path.join(args.log_dir, "preprocess_news_bert.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(report + "\n" + "=" * 70 + "\n")
    print(f"Log ditambahkan ke: {log_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 1:
        self_check()
    else:
        main()
