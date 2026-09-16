# Log Keputusan Desain — Jalur TF-IDF

Proyek: *Prediksi Peristiwa Geopolitik Global: Menganalisis Dampak Terhadap Nilai Tukar Dolar*
Dokumen ini isinya keputusan desain yang PERLU dijelaskan di laporan/Google Docs,
plus alasannya (why), bukan cuma what. Ditulis dari sisi pipeline TF-IDF
(`src/preprocess_news_tfidf.py`, `src/preprocess_kurs.py`, `src/align.py`,
`src/train_tfidf.py`). Jalur BERT ditangani terpisah oleh anggota tim lain.

---

## 1. Akuisisi data

- Sumber: CNBC (via endpoint pencarian internal Queryly) untuk berita, JISDOR
  (Bank Indonesia) untuk kurs referensi USD/IDR.
- Rentang tanggal: 2021-09-01 s.d. 2026-09-01 (`config.py: START_DATE/END_DATE`).
- Strategi filter tahap 1 = pemilihan keyword pencarian, dikelompokkan jadi
  4 tema: `conflict`, `policy`, `energy_supply`, dan `macro_control` (kelompok
  kontrol non-geopolitik, dipisah karena kebijakan moneter AS adalah confounder
  terkuat untuk USD/IDR — supaya efek geopolitik tidak tercampur dengan efek
  suku bunga The Fed).
- Hasil scraping mentah: **6.770 artikel** (`data/raw/cnbc_raw.csv`), tiap
  baris punya `title`, `description`, DAN `body` (isi artikel penuh).

## 2. Pembersihan teks & filter relevansi (`preprocess_news_tfidf.py`)

### 2.1 Urutan tahap (disengaja, bukan acak)
1. Dedup URL, lalu dedup judul ternormalisasi (CNBC kadang menerbitkan ulang
   artikel yang sama dengan URL beda).
2. Buang tipe non-artikel (video, slideshow, quote, dst).
3. Normalisasi Unicode/HTML + hapus boilerplate CNBC ("Sign up for...", dst).
4. Filter panjang minimum (`MIN_TOKENS = 5`).
5. **Filter relevansi tahap-2**: skoring leksikon berbobot (`GEO_LEXICON`,
   threshold `RELEVANCE_THRESHOLD = 2`) + leksikon negatif (`NEGATIVE_LEXICON`)
   yang otomatis menolak artikel non-geopolitik (resep, olahraga, dst).

### 2.2 BUG yang ditemukan & diperbaiki: skoring relevansi HARUS dari title+desc, bukan body
Awalnya kami mencoba menggabungkan `title + description + body` sebelum
skoring relevansi. Hasilnya: **2.972 artikel yang jelas-jelas relevan
(skor leksikon sampai 22) salah ditolak**, karena satu kata di
`NEGATIVE_LEXICON` (mis. "hiring", "earnings beat") kebetulan nyangkut di
suatu paragraf `body` yang panjang (rata-rata ~575 kata) dan tidak
berhubungan dengan topik utama artikel.

**Perbaikan**: `relevance_score` dan `has_negative` tetap dihitung dari
`text_for_filter` (title+description saja, sesuai kalibrasi awal leksikon).
`body` tetap digabung ke teks final (`text_clean` intermediate → `text_norm`),
tapi TIDAK ikut jadi basis keputusan filter. Setelah perbaikan, jumlah
artikel lolos kembali ke 4.116 (sama seperti sebelum body ditambahkan) —
membuktikan filter relevansi title+desc tidak terpengaruh, sementara teks
akhir tetap lebih kaya karena memuat isi artikel penuh.

### 2.3 Tabel penyusutan data
| Tahap | Baris | Perubahan |
|---|---|---|
| 0. Data mentah | 6.770 | — |
| 1. Dedup URL | 6.770 | 0% |
| 2. Dedup judul | 6.765 | -0.1% |
| 3. Buang non-artikel | 6.709 | -0.8% |
| 4. Filter panjang (≥5 token) | 6.709 | 0% |
| 5. Filter relevansi (skor ≥2, tanpa leksikon negatif) | 4.116 | -38.6% |
| 6. Validasi timestamp | 4.116 | 0% |
| 7. Punya `target_date` valid (alignment) | 4.109 | -0.2% |

Artikel yang ditolak tetap disimpan di `data/interim/cnbc_rejected.csv`
sebagai bukti kerja filter (bisa dipakai untuk contoh konkret di laporan).

### 2.4 Aturan tokenisasi TF-IDF (`text_norm`)
`text_norm` = lowercase, HTML/URL/boilerplate dibuang, stopword dibuang,
**tanpa stemming**. Simbol yang DIPERTAHANKAN cuma tiga: `.` `$` `%`
(mis. `"$100"`, `"3.5"`, `"8%"` tetap utuh) — simbol lain (`'`, `-`, dll.)
dibuang, sehingga kata bersambung seperti "co-founder" pecah jadi dua token
terpisah ("co", "founder"). Alasan `.` `$` `%` dipertahankan:

- **Angka & magnitudo (`$`, `%`)**: "oil surges 8%" dan "sanksi $100 miliar"
  — besaran adalah sinyal ekonomi, bukan noise yang boleh dibuang.
- **Titik (`.`)**: menandai desimal (`"3.5"`) dan singkatan (`"U.S."`).
- **Kata negasi** (`not`, `no`, `never`, `without`, dst) SENGAJA tidak masuk
  daftar stopword — daftar stopword standar (NLTK dkk.) akan membalik makna
  kalimat sentimen ("not escalating" → "escalating" kalau "not" dibuang).
- **Stemming dilewati** — pada korpus penuh nama diri (Russia, OPEC, Iran),
  stemming agresif lebih sering merusak ("Chinese" → "chines") daripada
  membantu.

### 2.5 Skema kolom final `news_tfidf_clean.csv`
`url, text_norm, section, published_utc, published_wib, relevance_score,
matched_terms, n_tokens, target_date, is_offhours, hours_to_fixing,
target_date_lag1`.

`title`, `description`, `body` mentah dan `title_clean`/`text_clean`
(jalur BERT) SENGAJA tidak disimpan di file ini — sudah ditangani di
pipeline BERT milik anggota tim lain. `article_id` juga didrop karena
nilainya identik dengan `url` (redundan). `relevance_score`/`matched_terms`
dipertahankan sebagai bukti audit kenapa suatu artikel lolos filter.

## 3. Pembersihan kurs JISDOR (`preprocess_kurs.py`)

- Menangani format angka Indonesia ("15.250,00" → 15250.0).
- **JISDOR TIDAK di-reindex ke kalender harian** dan TIDAK di-forward-fill.
  Hari tanpa fixing (weekend, libur nasional) dibiarkan hilang dari data —
  ini justru mendefinisikan kalender hari kerja BI secara otomatis tanpa
  library hari libur eksternal.
- Hasil: **1.156 hari kerja BI** (2021-09-09 s.d. 2026-09-01).
- Label arah (`direction`) pakai zona mati (`FLAT_THRESHOLD = 0.0005` log-return):
  `up` 593 hari, `down` 436 hari, `flat` 127 hari.

## 4. Penyelarasan waktu berita ↔ kurs (`align.py`)

### 4.1 Kenapa bukan "samakan UTC vs WIB"?
JISDOR cuma punya **tanggal** (satu fixing/hari, tanpa jam) — jadi tanggal itu
sendiri sudah implisit WIB, tidak ada yang perlu dikonversi. Yang dikonversi
justru timestamp berita CNBC: dari UTC (`published_utc`) ke WIB
(`published_wib`, `tz_convert("Asia/Jakarta")`).

### 4.2 Aturan cutoff & roll-forward
JISDOR dihitung dari transaksi antarbank jendela 08:00–09:45 WIB, publikasi
10:00 WIB. Aturan:
- Berita terbit **< 08:00 WIB** → berpotensi memengaruhi fixing HARI ITU.
- Berita terbit **≥ 08:00 WIB** (termasuk semua berita malam/sore) →
  digulirkan maju (roll-forward) ke fixing hari kerja BI BERIKUTNYA.
- Kalau hasilnya bukan hari kerja BI (weekend/libur), gulirkan lagi ke hari
  kerja BI terdekat berikutnya.

Cutoff dipasang di 08:00 (bukan jam publikasi 10:00) supaya konservatif —
berita jam 09:30 secara teknis terbit sebelum publikasi resmi, tapi
informasinya sudah terserap sebagian ke transaksi yang membentuk fixing itu;
memakainya sebagai prediktor = *look-ahead bias* halus.

Roll-forward dipilih (bukan dibuang atau roll-backward) karena membuang
berita akhir pekan berarti membuang ~28% korpus, padahal justru peristiwa
akhir pekan (invasi, kudeta, keputusan OPEC) yang paling sering
menggerakkan pasar. Roll-backward mustahil secara kausal.

### 4.3 Temuan: jendela Senin lebih lebar TAPI publikasi lebih sepi
Verifikasi bahwa roll-forward bekerja: `window_hours` rata-rata Senin
**62,85 jam** vs hari lain **~30 jam** (≈2x lipat, sesuai jendela Jumat
08:00 → Senin 08:00). TAPI rata-rata `n_news` mentah Senin **tidak** ikut
naik 2x — malah relatif rendah. Setelah dicek per jam (`n_news / window_hours`):
Senin 0,053 berita/jam vs hari lain 0,096–0,131 berita/jam. Artinya volume
publikasi CNBC di akhir pekan memang jauh lebih sepi, bukan bug alignment.

**Implikasi untuk laporan**: jangan bandingkan `n_news` mentah antar hari;
gunakan `n_news` bersama `window_hours` (mis. rasio `n_news/window_hours`)
sebagai kontrol saat modeling atau analisis deskriptif.

### 4.4 Cakupan alignment
84,0% hari kerja BI (971 dari 1.156) punya ≥1 berita geopolitik yang
match keyword; 185 hari tidak punya berita sama sekali (dipertahankan di
`aligned_daily.csv` dengan `n_news=0`, `text_norm_concat=""` — ketiadaan
berita adalah informasi, bukan data yang harus dibuang, supaya kontinuitas
deret waktu kurs tidak rusak). Rata-rata 3,6 berita/hari, median 2.

## 5. Baseline model: TF-IDF + Logistic Regression (`train_tfidf.py`)

### 5.1 Setup
- Unit analisis: **per hari** (bukan per artikel), karena target (`direction`)
  adalah label harian. Fitur teksnya `text_norm_concat` dari `aligned_daily.csv`.
- Hari dengan `n_news = 0` DIBUANG dari training (dokumen kosong tidak
  membawa sinyal, hanya mencemari classification report) — 185 hari dibuang,
  tersisa **971 hari**.
- Split **kronologis 80/20** (bukan acak) — 776 hari train
  (2021-09-09 s.d. 2025-09-05), 195 hari test (2025-09-07 s.d. 2026-09-01).
  Random split akan membuat model "mengintip" kosakata dari peristiwa masa
  depan (mis. "houthi" cuma muncul mulai 2024) untuk memprediksi masa lalu.
- `TfidfVectorizer`: `min_df=5`, `max_df=0.8`, `ngram_range=(1,2)`,
  `max_features=5000`.
- `LogisticRegression(class_weight="balanced")` — dipilih karena kelas
  `flat` cuma ~11% data; tanpa pembobotan, model paling gampang menang
  dengan selalu menebak `up`.

### 5.2 Hasil (JUJUR, tidak dipoles)
| Metrik | Dummy (selalu tebak mayoritas) | Logistic Regression |
|---|---|---|
| Akurasi | 0,518 | 0,446 |

Classification report per kelas (test set, 195 hari):

| Kelas | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| down | 0,38 | 0,75 | 0,50 | 69 |
| flat | 0,00 | 0,00 | 0,00 | 25 |
| up | 0,61 | 0,35 | 0,44 | 101 |

**Interpretasi**: model TF-IDF + Logistic Regression baseline **kalah dari
baseline naif** dalam akurasi mentah. Ini finding yang valid untuk
dilaporkan, bukan kegagalan eksperimen — konsisten dengan literatur bahwa
sinyal teks berita saja punya daya prediksi lemah untuk arah kurs jangka
pendek (pasar valas sangat likuid dan cepat menyerap informasi publik/*semi
strong-form efficiency*). Trade-off `class_weight="balanced"`: recall kelas
`down` naik jadi 0,75 (model jadi lebih sensitif ke sinyal turun) dengan
kompensasi akurasi keseluruhan turun; kelas `flat` sama sekali tidak
terdeteksi (recall 0) — kemungkinan karena sinyal linguistik untuk "kurs
nyaris tidak bergerak" memang tidak ada (secara intuisi masuk akal: tidak
ada kata kunci yang berarti "tidak terjadi apa-apa").

**Batasan yang perlu ditulis eksplisit di laporan**:
1. Baseline ini pakai representasi TF-IDF polos, tanpa seleksi fitur/feature
   engineering tambahan (mis. sentiment score, count berita per kelompok
   keyword, lag fitur kurs sendiri).
2. Test set (195 hari, 2025-09 s.d. 2026-09) mewakili satu periode waktu
   spesifik — akurasi bisa berbeda di periode lain (rezim pasar berubah).
3. Term berbobot tertinggi per kelas (lihat `logs/train_tfidf_report.txt`)
   berguna untuk analisis kualitatif meski akurasi kuantitatif lemah — mis.
   term "china", "opec", "geopolitical" berasosiasi kuat dengan kelas `up`.

## 6. Ringkasan file & artefak

| File | Isi |
|---|---|
| `data/raw/cnbc_raw.csv` | 6.770 artikel mentah (title, description, body) |
| `data/interim/cnbc_rejected.csv` | Artikel yang ditolak filter relevansi (bukti audit) |
| `data/processed/news_tfidf_clean.csv` | 4.109 artikel, jalur TF-IDF (`text_norm` + metadata) |
| `data/processed/kurs_clean.csv` | 1.156 hari kerja BI, label `direction` |
| `data/processed/aligned_daily.csv` | Gabungan harian: kurs + `text_norm_concat` + kontrol (`window_hours`, dst.) |
| `logs/train_tfidf_report.txt` | Output lengkap `train_tfidf.py` (metrik, confusion matrix, top term per kelas) |
