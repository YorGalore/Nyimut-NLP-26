"""
config.py
=========
Pusat SEMUA keputusan desain pipeline Tugas 1.

Kenapa dipisah ke satu file?
Karena saat evaluasi, tim harus bisa menjelaskan setiap keputusan (leksikon,
threshold, cutoff jam, dst). Dengan semuanya di sini, kalian tinggal membuka
satu file untuk menunjukkan "ini semua parameter yang kami pilih, dan ini
alasannya" -- bukan berburu angka ajaib yang tersebar di 4 skrip.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# 1. PATH
# ---------------------------------------------------------------------------
# Path relatif terhadap root repo, dihitung dari lokasi file ini (src/)
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

NEWS_CLEAN_CSV = DATA_PROCESSED / "news_clean.csv"
KURS_CLEAN_CSV = DATA_PROCESSED / "kurs_clean.csv"
ALIGNED_DAILY_CSV = DATA_PROCESSED / "aligned_daily.csv"

# ---------------------------------------------------------------------------
# 2. RENTANG WAKTU (sesuai ketentuan tugas)
# ---------------------------------------------------------------------------
START_DATE = "2021-09-01"
END_DATE = "2026-09-01"

# ---------------------------------------------------------------------------
# 3. ENDPOINT PENCARIAN INTERNAL CNBC
# ---------------------------------------------------------------------------
# CNBC memakai vendor pencarian pihak ketiga bernama Queryly. Endpoint di bawah
# ini adalah endpoint yang dipanggil browser saat kita mengetik di kotak
# pencarian cnbc.com.
#
# !! WAJIB DIVERIFIKASI SENDIRI SEBELUM RUN PENUH !!
#   1. Buka https://www.cnbc.com/search/?query=sanctions&qsearchterm=sanctions
#   2. F12 -> tab Network -> filter Fetch/XHR -> refresh
#   3. Cari request "json.aspx" ke domain api.queryly.com
#   4. Salin nilai parameter queryly_key ke bawah ini
#
# Kunci ini bisa berubah sewaktu-waktu. Kalau respons kosong / 403,
# penyebab nomor satu adalah key yang sudah tidak berlaku.
QUERYLY_ENDPOINT = "https://api.queryly.com/cnbc/json.aspx"
QUERYLY_KEY = "31a35d40a9a64ab3"

BATCH_SIZE = 100          # jumlah hasil per request (maksimum yang diterima Queryly)
MAX_ENDINDEX = 1000       # batas offset. Queryly umumnya menolak offset sangat besar.
                          # Solusi kita bukan menaikkan ini, tapi memperbanyak keyword.

REQUEST_TIMEOUT = 20
SLEEP_MIN = 1.0           # jeda antar request (detik) -- sopan + hindari rate limit
SLEEP_MAX = 2.0
MAX_RETRY = 3

# User-Agent browser asli. Tanpa ini banyak endpoint membalas 403.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.cnbc.com/search/",
}

# ---------------------------------------------------------------------------
# 4. KEYWORD PENCARIAN = STRATEGI FILTERING TAHAP 1
# ---------------------------------------------------------------------------
# Kita tidak bisa "ambil semua berita CNBC" -- API pencarian butuh query.
# Justru itu keuntungan: pemilihan keyword INI adalah filter tahap pertama kita.
#
# Dikelompokkan supaya di laporan bisa dijelaskan per tema, dan supaya nanti
# di Tugas 2-4 bisa dilakukan ablation per kelompok.
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
    # --- KELOMPOK KONTROL, BUKAN GEOPOLITIK ---
    # Kebijakan moneter AS adalah confounder TERKUAT untuk pergerakan USD.
    # Kalau dicampur ke kelompok geopolitik, kita tidak akan bisa membuktikan
    # bahwa efek yang terlihat memang berasal dari geopolitik.
    # Karena itu diberi label terpisah: bisa di-include/exclude saat modeling.
    "macro_control": [
        "Federal Reserve", "interest rate decision", "US inflation",
        "dollar index", "Treasury yields", "rupiah exchange rate",
        "Bank Indonesia", "emerging market currency",
    ],
}

# ---------------------------------------------------------------------------
# 5. FILTER RELEVANSI TAHAP 2 (leksikon berbobot)
# ---------------------------------------------------------------------------
# Search engine mengembalikan hasil yang longgar. Query "strike" bisa
# memunculkan berita mogok kerja buruh pabrik, bukan serangan militer.
# Jadi kita skor ulang judul+deskripsi dengan leksikon ini.
#
# Bobot 2 = istilah yang hampir pasti geopolitik.
# Bobot 1 = istilah pendukung yang bisa ambigu sendirian.
GEO_LEXICON = {
    # bobot 2
    "sanction": 2, "sanctions": 2, "tariff": 2, "tariffs": 2, "embargo": 2,
    "invasion": 2, "airstrike": 2, "ceasefire": 2, "warfare": 2,
    "geopolitical": 2, "opec": 2, "nato": 2, "annexation": 2, "coup": 2,
    "export controls": 2, "trade war": 2, "missile": 2, "warship": 2,
    # bobot 1
    "war": 1, "conflict": 1, "military": 1, "troops": 1, "diplomatic": 1,
    "tension": 1, "tensions": 1, "retaliation": 1, "escalation": 1,
    "russia": 1, "ukraine": 1, "israel": 1, "gaza": 1, "iran": 1,
    "china": 1, "taiwan": 1, "north korea": 1, "kremlin": 1, "beijing": 1,
    "oil": 1, "crude": 1, "pipeline": 1, "supply chain": 1, "blockade": 1,
    "treaty": 1, "summit": 1, "border": 1, "defense": 1, "security council": 1,
}

# Ambang minimum skor agar sebuah artikel dianggap relevan.
# 2 berarti: satu istilah bobot-2, ATAU dua istilah bobot-1.
# Threshold ini sengaja rendah (recall > precision) karena di tahap akuisisi
# data, membuang berita relevan lebih mahal daripada menyimpan sedikit noise.
RELEVANCE_THRESHOLD = 2

# Leksikon negatif: kalau muncul, artikel langsung ditolak apapun skornya.
NEGATIVE_LEXICON = [
    "best credit card", "recipe", "celebrity", "box office", "nfl", "nba",
    "super bowl", "how to save money", "gift guide", "black friday deal",
    "horoscope", "royal family", "movie review", "album review",
    "fantasy football", "product review", "prime day",
]

# Tipe konten yang dibuang: bukan artikel teks.
DROP_TYPES = {"cnbcvideo", "video", "slideshow", "livestream", "wildcard", "blog"}
DROP_SECTION_KEYWORDS = ["pro:", "quote", "make it", "select", "press release"]

MIN_TOKENS = 5   # dokumen lebih pendek dari ini tidak membawa informasi

# ---------------------------------------------------------------------------
# 6. BOILERPLATE CNBC
# ---------------------------------------------------------------------------
# Kalimat berulang yang muncul di ribuan artikel. Kalau dibiarkan, frasa ini
# akan mendominasi TF-IDF dan menenggelamkan sinyal yang sebenarnya.
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

# ---------------------------------------------------------------------------
# 7. STOPWORDS UNTUK JALUR text_norm
# ---------------------------------------------------------------------------
# CATATAN PENTING (tulis ini di laporan):
# Daftar stopword standar (mis. NLTK) membuang kata negasi seperti "not",
# "no", "never". Untuk analisis sentimen berita, itu MEMBALIK makna kalimat
# ("not escalating" jadi "escalating"). Karena itu kata negasi sengaja
# TIDAK dimasukkan ke daftar di bawah.
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
# Kata yang eksplisit DIPERTAHANKAN meski mirip stopword:
# not, no, nor, never, without, against, before, after, between
# (tidak perlu ditulis di sini -- cukup tidak dimasukkan ke STOPWORDS)

# ---------------------------------------------------------------------------
# 8. ATURAN PENYELARASAN TEMPORAL
# ---------------------------------------------------------------------------
TZ_NEWS = "UTC"            # timestamp CNBC dalam UTC
TZ_MARKET = "Asia/Jakarta" # WIB = UTC+7

# JISDOR dibentuk dari transaksi antarbank pada jendela 08:00-09:45 WIB dan
# dipublikasikan pukul 10:00 WIB.
#
# Cutoff kita tetapkan di 08:00, BUKAN 10:00. Alasannya:
# berita yang terbit pukul 09:30 memang muncul sebelum publikasi jam 10:00,
# tetapi informasinya sudah sebagian terserap ke dalam harga yang membentuk
# fixing tersebut. Memakainya sebagai prediktor = look-ahead bias.
# 08:00 adalah pilihan konservatif yang aman.
ALIGNMENT_CUTOFF_HOUR = 8

# Ambang "tidak bergerak" untuk label arah (dalam log-return).
# 0.0005 = 0.05%. Pergerakan di bawah ini dianggap noise, bukan sinyal.
FLAT_THRESHOLD = 0.0005