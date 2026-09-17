import html
import re
import unicodedata
import pandas as pd
import config as C


# regex dikompilasi sekali di awal (dipakai puluhan ribu kali)
RE_TAG = re.compile(r"<[^>]+>")
RE_URL = re.compile(r"https?://\S+|www\.\S+")
RE_WS = re.compile(r"\s+")
RE_ZEROWIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")
RE_BOILER = [re.compile(p, re.IGNORECASE) for p in C.BOILERPLATE_PATTERNS]
RE_TITLE_NORM = re.compile(r"[^a-z0-9 ]")
RE_TOKEN = re.compile(r"[a-z0-9%$][a-z0-9%$.]*")
LEX_PATTERNS = {
    term: re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
    for term in C.GEO_LEXICON
}
NEG_PATTERNS = [
    re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE) for t in C.NEGATIVE_LEXICON
]



# pembersihan karakter dan boilerplate
def clean_text(text):
    #menghasilkan text_clean
    if not isinstance(text, str):
        return ""
    
    t = html.unescape(html.unescape(text))
    t = RE_TAG.sub(" ", t)          # sisa tag HTML
    t = RE_URL.sub(" ", t)          # URL tidak membawa makna semantik
    t = RE_ZEROWIDTH.sub("", t)     # zero-width & directional marks
    t = unicodedata.normalize("NFKC", t)

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
    #menghasilkan text_norm
    if not text:
        return ""
    tokens = RE_TOKEN.findall(text.lower())
    tokens = [tok.strip(".") for tok in tokens]
    tokens = [tok for tok in tokens if tok and tok not in C.STOPWORDS and len(tok) > 1]
    return " ".join(tokens)



# skoring relevansi
def relevance_score(text):
    score, matched = 0, []

    for term, weight in C.GEO_LEXICON.items():
        if LEX_PATTERNS[term].search(text):
            score += weight
            matched.append(term)
    return score, matched


def has_negative(text):
    return any(p.search(text) for p in NEG_PATTERNS)

def main():
    df = pd.read_csv(C.CNBC_RAW_CSV)
    log = [("0. Data mentah", len(df))]

    # gabungkan jejak keyword sebelum dedup 
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

    # dedup berdasarkan URL 
    df = df.drop_duplicates(subset=["url"], keep="first")
    df = df.merge(kw_agg, on="url", how="left")
    df = df.drop(columns=["search_keyword", "keyword_group"], errors="ignore")
    log.append(("1. Setelah dedup URL", len(df)))

    # dedup judul ternormalisasi 
    df["_title_key"] = (
        df["title"].astype(str).str.lower().apply(lambda s: RE_TITLE_NORM.sub("", s).strip())
    )
    df = df.drop_duplicates(subset=["_title_key"], keep="first")
    log.append(("2. Setelah dedup judul", len(df)))

    # buang tipe non-artikel 
    type_l = df["type"].fillna("").astype(str).str.lower()
    sect_l = df["section"].fillna("").astype(str).str.lower()
    mask_type = type_l.isin(C.DROP_TYPES)
    mask_sect = sect_l.apply(lambda s: any(k in s for k in C.DROP_SECTION_KEYWORDS))
    df = df[~(mask_type | mask_sect)]
    log.append(("3. Setelah buang video/non-artikel", len(df)))

    # bersihkan teks
    df["title_clean"] = df["title"].apply(clean_text)
    df["desc_clean"] = df["description"].apply(clean_text)
    df["body_clean"] = df["body"].apply(clean_text) if "body" in df.columns else ""

    # untuk skoring relevansi & leksikon negatif
    df["text_for_filter"] = df.apply(
        lambda r: ". ".join(p for p in (r["title_clean"], r["desc_clean"]) if p),
        axis=1,
    )

    # text_clean 
    df["text_clean"] = df.apply(
        lambda r: ". ".join(p for p in (r["title_clean"], r["desc_clean"], r["body_clean"]) if p),
        axis=1,
    )

    # filter panjang
    df["n_tokens"] = df["text_clean"].str.split().str.len()
    df = df[df["n_tokens"] >= C.MIN_TOKENS]
    log.append((f"4. Setelah filter panjang (>= {C.MIN_TOKENS} token)", len(df)))

    # relevansi
    scored = df["text_for_filter"].apply(relevance_score)
    df["relevance_score"] = [s for s, _ in scored]
    df["matched_terms"] = ["|".join(m) for _, m in scored]
    df["has_negative"] = df["text_for_filter"].apply(has_negative)

    keep = (df["relevance_score"] >= C.RELEVANCE_THRESHOLD) & (~df["has_negative"])

    # simpan yang ditolak juga
    df[~keep].to_csv(C.NEWS_REJECTED_CSV, index=False)
    df = df[keep]
    log.append((f"5. Setelah filter relevansi (skor >= {C.RELEVANCE_THRESHOLD})", len(df)))

    # text_norm 
    df["text_norm"] = df["text_clean"].apply(normalize_text)

    # simpan UTC dan WIB 
    df["published_utc"] = pd.to_datetime(
        df["published"], utc=True, errors="coerce", format="mixed"
    )
    df = df.dropna(subset=["published_utc"])
    df["published_wib"] = df["published_utc"].dt.tz_convert(C.TZ_MARKET)
    log.append(("6. Setelah validasi timestamp", len(df)))

    # kolom final 
    cols = [
        "url", "text_norm",
        "section", "published_utc", "published_wib",
        "relevance_score", "matched_terms",
    ]
    out = df[[c for c in cols if c in df.columns]].sort_values("published_utc")
    out.to_csv(C.NEWS_TFIDF_CSV, index=False)

    # laporan penyusutan 
    print("\nPENYUSUTAN DATA PER TAHAP")
    print("-" * 55)
    prev = log[0][1]
    for label, n in log:
        pct = f"{(n/prev*100 - 100):+.1f}%" if prev else ""
        print(f"  {label:<48s} {n:>7,}  {pct}")
        prev = n
    print("-" * 55)
    print(f"Tersimpan: {C.NEWS_TFIDF_CSV}")
    print(f"Ditolak  : {C.NEWS_REJECTED_CSV}")
    print(f"\nTerm leksikon relevansi yang paling sering match (top 15):")
    print(out["matched_terms"].str.split("|").explode().value_counts().head(15).to_string())


if __name__ == "__main__":
    main()