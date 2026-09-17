from pathlib import Path


# path relatif terhadap root repo, dihitung dari lokasi file ini (src/)
ROOT = Path(__file__).resolve().parent.parent

DATA_RAW = ROOT / "data" / "raw"
DATA_INTERIM = ROOT / "data" / "interim"
DATA_PROCESSED = ROOT / "data" / "processed"
CHECKPOINT_DIR = DATA_RAW / "checkpoints"

for _d in (DATA_RAW, DATA_INTERIM, DATA_PROCESSED, CHECKPOINT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

CNBC_RAW_CSV = DATA_RAW / "cnbc_raw.csv"
JISDOR_RAW_CSV = DATA_RAW / "jisdor_raw.csv"
NEWS_DEDUP_CSV = DATA_INTERIM / "cnbc_dedup.csv"
NEWS_REJECTED_CSV = DATA_INTERIM / "cnbc_rejected.csv"  # bukti kerja filter
NEWS_TFIDF_CSV = DATA_PROCESSED / "news_tfidf_clean.csv"
KURS_CLEAN_CSV = DATA_PROCESSED / "kurs_clean.csv"
ALIGNED_DAILY_CSV = DATA_PROCESSED / "aligned_daily.csv"
START_DATE = "2021-09-01"
END_DATE = "2026-09-01"

# 2. Endpoint pencarian internal CNBC (Queryly) dan parameter request
QUERYLY_ENDPOINT = "https://api.queryly.com/cnbc/json.aspx"
QUERYLY_KEY = "31a35d40a9a64ab3"

BATCH_SIZE = 100          #
MAX_ENDINDEX = 1000      
REQUEST_TIMEOUT = 20
SLEEP_MIN = 1.0           # jeda antar request (detik)
SLEEP_MAX = 2.0
MAX_RETRY = 3

# user-agent browser asli
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.cnbc.com/search/",
}

# keyword untuk mengklasifikasikan berita geopolitik vs non-geopolitik
SEARCH_KEYWORDS = {
    "conflict": [
        "war", "invasion", "military strike", "airstrike", "ceasefire",
        "troops deployed", "armed conflict", "missile attack", "border clash",
        "Russia Ukraine", "Israel Gaza", "Middle East conflict",
        "Taiwan tensions", "South China Sea", "North Korea missile",
    ],

    "policy": [
        "sanctions", "tariffs", "trade war", "export controls", "embargo",
        "trade restrictions", "geopolitical risk", "diplomatic crisis",
        "US China tensions", "chip export ban", "asset freeze",
        "NATO", "summit talks", "peace deal",
    ],

    "energy_supply": [
        "OPEC", "oil supply", "oil prices surge", "energy crisis",
        "gas pipeline", "crude output cut", "shipping disruption",
        "Red Sea shipping", "Strait of Hormuz", "supply chain disruption",
    ],
    
    "macro_control": [
        "Federal Reserve", "interest rate decision", "US inflation",
        "dollar index", "Treasury yields", "rupiah exchange rate",
        "Bank Indonesia", "emerging market currency",
    ],
}

# filtering berita geopolitik: leksikon, ambang skor, dan stopwords
GEO_LEXICON = {
    # bobot 2
    "sanction": 2, "sanctions": 2, "tariff": 2, "tariffs": 2, "embargo": 2,
    "invasion": 2, "airstrike": 2, "ceasefire": 2, "warfare": 2,
    "geopolitical": 2, "opec": 2, "nato": 2, "annexation": 2, "coup": 2,
    "export controls": 2, "trade war": 2, "missile": 2, "warship": 2,

    #tambahan
    "hormuz": 2, "red sea": 2, "houthi": 2, "zelenskyy": 2, "putin": 2, 
    "kyiv": 2, "moscow": 1, "hamas": 2, "hezbollah": 2, "netanyahu": 1,
    "tehran": 2, "pyongyang": 2, "xi jinping": 1, "geopolitics": 2,
    "trade deal": 1, "import duty": 2, "export ban": 2, "opec+": 2,
    "strait": 1, "annex": 2, "proxy war": 2, "arms": 1, "beijing": 1, "us china tensions": 2, "chinese military": 2,
    "south china sea": 2, "chip export": 2,

    # bobot 1
    "war": 1, "conflict": 1, "military": 1, "troops": 1, "diplomatic": 1,
    "tension": 1, "tensions": 1, "retaliation": 1, "escalation": 1,
    "russia": 1, "ukraine": 1, "israel": 1, "gaza": 1, "iran": 1,
    "taiwan": 1, "north korea": 1, "kremlin": 1, "beijing": 1,
    "oil": 1, "crude": 1, "pipeline": 1, "blockade": 1,
    "treaty": 1, "summit": 1, "border": 1, "defense": 1, "security council": 1,
}

# ambang minimum skor agar sebuah artikel dianggap relevan
RELEVANCE_THRESHOLD = 2

# leksikon negatif: kalau muncul, artikel langsung ditolak apapun skornya
NEGATIVE_LEXICON = [
    "best credit card", "recipe", "celebrity", "box office", "nfl", "nba",
    "super bowl", "how to save money", "gift guide", "black friday deal",
    "horoscope", "royal family", "movie review", "album review",
    "fantasy football", "product review", "prime day", "gaming stocks", "hire", "hiring", "holiday season", "earnings beat",
    "quarterly results", "stocks to buy", "analyst upgrade",
]

# tipe konten yang dibuang: bukan artikel teks
DROP_TYPES = {"cnbcvideo", "video", "slideshow", "livestream", "wildcard", "blog"}
DROP_SECTION_KEYWORDS = ["pro:", "quote", "make it", "select", "press release"]
MIN_TOKENS = 5   # dokumen lebih pendek dari ini tidak membawa informasi

# boilerplate CNBC
BOILERPLATE_PATTERNS = [
    r"Sign up (for|now)[^.]*\.",
    r"Subscribe to CNBC[^.]*\.",
    r"Got a confidential news tip\?[^.]*\.?",
    r"[—\-]\s*CNBC'?s [^.]*contributed to this (report|story)\.",
    r"Watch CNBC'?s full interview[^.]*\.",
    r"Read more:[^.]*\.?",
    r"Correction:\s*This (story|article)[^.]*\.",
    r"Disclosure:[^.]*\.",
    r"This is breaking news\.?\s*(Please )?check back for updates\.?",
    r"In this article:?",
    r"Don'?t miss[^.]*\.",
]

# stopwords untuk jalur text_norm
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "while", "of", "at", "by",
    "for", "with", "about", "into", "through", "during", "to", "from", "in",
    "on", "off", "over", "under", "again", "then", "once", "here", "there",
    "all", "any", "both", "each", "few", "more", "most", "other", "some",
    "such", "than", "too", "very", "can", "will", "just", "should", "now",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "doing", "would", "could", "this", "that", "these",
    "those", "i", "you", "he", "she", "it", "we", "they", "them", "his",
    "her", "its", "their", "our", "as", "so", "up", "out", "also", "said",
}

# aturan penyelarasan waktu
TZ_NEWS = "UTC"            # timestamp CNBC dalam UTC
TZ_MARKET = "Asia/Jakarta" # WIB = UTC+7
ALIGNMENT_CUTOFF_HOUR = 8
FLAT_THRESHOLD = 0.0005