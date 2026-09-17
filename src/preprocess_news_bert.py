import html
import re
import unicodedata
import pandas as pd
import config as C
from align import build_assigner  


# normalisasi karakter
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
RE_LEADING_WIDGET = re.compile(r"^\s*In this article\s*", re.IGNORECASE)
RE_TRAILING_CRAMER = re.compile(
    r"Click here to read Jim Cramer's Guide to Investing.*$",
    re.IGNORECASE | re.DOTALL,
)

# akhir kalimat yang aman": [^.]*\. polos berhenti tepat di tengah singkatan
SENT_END = r"(?:U\.S\.|U\.K\.|U\.N\.|E\.U\.|[^.])*\."

# dihapus hanya kalimat yang cocok, sisanya utuh
BOILERPLATE_PATTERNS = [
    r"Sign up (for|now)" + SENT_END,                       # 0/176 rusak di body
    r"Subscribe to CNBC on YouTube\.",                      # bentuk tetap, 39x
    r"Subscribe to CNBC PRO for exclusive insights and analysis, "
    r"and live business day programming from around the world\.",  # bentuk tetap, 18x
    r"[—\-]\s*CNBC'?s [^.]*contributed to this (report|story)\.",  # selalu diakhiri kata tetap
    r"Correction:\s*This (story|article)" + SENT_END,       # diperbaiki dgn SENT_END
    r"Disclosure:" + SENT_END,                              # 0/50 rusak di body
    r"This is breaking news\.?\s*(Please )?check back for updates\.?",
    r"This report is from today'?s CNBC Daily Open[^.]*\.\s*"
    r"CNBC Daily Open brings investors up to speed[^.]*\.\s*"
    r"Like what you see\?\s*You can subscribe here\s*\.",
]
RE_BOILER = [re.compile(p, re.IGNORECASE) for p in BOILERPLATE_PATTERNS]

def clean_text(text):
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
    # bukti bahwa cleaning tidak merusak sinyal yang harus dipertahankan
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
            "Correction: This story has been updated to remove an incorrect "
            "reference to where U.S. Deputy Treasury Secretary Wally Adeyemo "
            "was speaking. Real reporting continues here.",
            "Real reporting continues here.",
        ),
        (
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


import argparse
import math
import os

CHUNK_MAX_LEN = 512   # batas token model (termasuk [CLS]/[SEP])
CHUNK_OVERLAP = 50     # overlap antar potongan untuk strategi B (chunking)


def n_chunks_needed(n_tokens, max_len=CHUNK_MAX_LEN, overlap=CHUNK_OVERLAP):
    # perkiraan jumlah potongan (chunk) yang dibutuhkan strategi
    if n_tokens <= max_len:
        return 1
    stride = max_len - overlap
    return 1 + math.ceil((n_tokens - max_len) / stride)

_TRADING_DATES = None  # cache, kurs_clean.csv dibaca sekali saja

def _get_trading_dates():
    global _TRADING_DATES
    if _TRADING_DATES is None:
        kurs = pd.read_csv(C.KURS_CLEAN_CSV)
        kurs["date"] = pd.to_datetime(kurs["date"], errors="coerce")
        _TRADING_DATES = sorted(kurs["date"].dt.date.unique())
    return _TRADING_DATES


def add_alignment_columns(df, dt_wib):
    # Menambahkan target_date, is_offhours, hours_to_fixing, target_date_lag1 
    trading_dates = _get_trading_dates()
    assign = build_assigner(trading_dates)

    df = df.copy()
    df["target_date"] = pd.to_datetime(dt_wib.apply(assign))

    df["is_offhours"] = (
        (dt_wib.dt.dayofweek >= 5) | (dt_wib.dt.hour >= C.ALIGNMENT_CUTOFF_HOUR)
    )
    df["hours_to_fixing"] = (
        df["target_date"]
        + pd.Timedelta(hours=C.ALIGNMENT_CUTOFF_HOUR)
        - dt_wib.dt.tz_localize(None)
    ).dt.total_seconds() / 3600

    next_map = {d: trading_dates[i + 1] for i, d in enumerate(trading_dates[:-1])}
    df["target_date_lag1"] = pd.to_datetime(df["target_date"].dt.date.map(next_map))

    return df


def build_dataset(df, tokenizer):
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

    # waktu disimpan dalam WIB 
    dt_utc = pd.to_datetime(df["published"], utc=True, errors="coerce", format="mixed")
    dt_wib = dt_utc.dt.tz_convert("Asia/Jakarta")
    df["_sort_dt"] = dt_wib
    df["date"] = dt_wib.dt.strftime("%Y-%m-%d %I:%M:%S %p WIB")

    df = add_alignment_columns(df, dt_wib)

    out_cols = [
        "url", "date", "title", "text_clean", "n_tokens",
        "needs_chunking", "n_chunks_est", "used_description_fallback", "section",
        "target_date", "is_offhours", "hours_to_fixing", "target_date_lag1",
    ]
    out = df[[c for c in out_cols if c in df.columns] + ["_sort_dt"]].sort_values("_sort_dt")
    out = out.drop(columns=["_sort_dt"])
    return out, log


def stratified_sample(df, n, seed=42):
    #Sampel acak terstratifikasi per tahun publikasi 
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
