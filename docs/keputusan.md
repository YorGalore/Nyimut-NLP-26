# Keputusan Proyek

Dokumen ini mencatat keputusan metodologis dan teknis yang diambil selama pengembangan proyek **Prediksi Peristiwa Geopolitik Global: Analisis Dampak Terhadap Nilai Tukar**. Setiap keputusan disertai alasan pemilihan serta alternatif yang dipertimbangkan agar proses penelitian dapat ditelusuri dan diaudit.

---

## 1. Pemilihan Sumber Data

### Keputusan
Menggunakan **CNBC** sebagai satu-satunya sumber berita geopolitik dan **JISDOR Bank Indonesia** sebagai sumber nilai tukar.

### Alasan
- CNBC menyediakan berita internasional yang relevan dengan peristiwa geopolitik dan memiliki keterkaitan dengan ekonomi serta pasar keuangan.
- Struktur artikel CNBC relatif konsisten sehingga mempermudah proses scraping dan preprocessing.
- JISDOR merupakan kurs referensi harian USD/IDR yang diterbitkan langsung oleh Bank Indonesia.
- Penggunaan satu sumber berita mengurangi kebutuhan penyelarasan skema dari beberapa sumber.
- Ketentuan tugas menetapkan Bank Indonesia sebagai sumber data nilai tukar.

### Alternatif yang Dipertimbangkan
Menggabungkan beberapa sumber berita untuk memperluas cakupan data.

### Alasan Tidak Dipilih
Penggabungan beberapa sumber akan menambah kompleksitas preprocessing, penyamaan format, deduplikasi lintas sumber, serta penyelarasan timestamp.

---

## 2. Pemilihan Metode Akuisisi CNBC

### Keputusan
Menggunakan **Playwright** untuk mengambil indeks artikel CNBC dari halaman archive.

### Alasan
Halaman archive CNBC menggunakan JavaScript untuk memuat dan merender elemen artikel. Playwright memungkinkan halaman dijalankan seperti browser sehingga elemen artikel dan tautannya dapat diidentifikasi.

### Alternatif yang Dipertimbangkan
Menggunakan HTTP request langsung atau melakukan scraping berdasarkan kategori politik.

### Alasan Tidak Dipilih
- Request langsung tidak selalu memperoleh elemen yang dirender secara dinamis.
- Halaman kategori politik CNBC tidak menyediakan seluruh artikel hingga periode yang dibutuhkan, terutama untuk artikel lama.
- Halaman archive memberikan pendekatan berbasis tanggal yang lebih sesuai dengan rentang waktu penelitian.

---

## 3. Pemilihan Strategi Filtering Berita

### Keputusan
Melakukan filtering dalam dua tahap:

1. Filtering berdasarkan judul.
2. Filtering berdasarkan konten artikel setelah full scraping.

### Alasan
Jumlah awal artikel sangat besar, yaitu **96.558 artikel**, sehingga mengambil isi penuh seluruh artikel sejak awal tidak efisien.

Filtering judul menggunakan lexicon geopolitik dapat mengurangi jumlah artikel yang perlu di-*fetch* sebelum proses scraping penuh.

### Alternatif yang Dipertimbangkan
Melakukan scraping isi penuh terhadap seluruh artikel kemudian melakukan klasifikasi relevansi.

### Alasan Tidak Dipilih
Pendekatan tersebut membutuhkan jauh lebih banyak request, waktu scraping, dan sumber daya komputasi.

---

## 4. Pemilihan Lexicon-Based Filtering

### Keputusan
Menggunakan **keyword/lexicon geopolitik** untuk tahap awal filtering judul.

### Alasan
- Sederhana dan mudah diaudit.
- Tidak membutuhkan model machine learning tambahan.
- Cepat diterapkan pada puluhan ribu artikel.
- Keyword dapat disesuaikan dengan ruang lingkup penelitian.

### Validasi
Metode diuji menggunakan audit manual terhadap **50 sampel acak** dan menghasilkan presisi sebesar **86%**.

### Catatan
Filtering berbasis lexicon digunakan sebagai tahap penyaringan awal, bukan sebagai klaim bahwa seluruh artikel yang lolos pasti relevan.

---

## 5. Pemilihan Sumber Utama Ekstraksi Artikel

### Keputusan
Menggunakan **JSON-LD sebagai sumber utama** untuk ekstraksi metadata dan isi artikel.

Urutan ekstraksi yang digunakan:

1. JSON-LD
2. Meta tag
3. CSS selector sebagai fallback

### Alasan
JSON-LD merupakan data terstruktur yang lebih stabil terhadap perubahan tampilan halaman dibandingkan selector CSS.

### Alasan Menggunakan Fallback
Struktur artikel CNBC dapat berbeda antara artikel lama dan baru. Oleh karena itu, meta tag dan CSS selector tetap disediakan untuk menangani artikel yang tidak lengkap pada lapisan sebelumnya.

---

## 6. Validasi CSS Selector

### Keputusan
Sebuah kandidat container artikel dari CSS selector hanya dianggap valid apabila mengandung minimal **3 elemen paragraf**.

### Alasan
Beberapa elemen halaman seperti widget "artikel terkait" dapat memiliki struktur yang menyerupai isi artikel.

Ambang minimal tiga paragraf digunakan untuk mengurangi risiko mengambil konten yang bukan merupakan badan artikel.

---

## 7. Penggunaan Checkpoint pada Scraping

### Keputusan
Menggunakan sistem checkpoint selama proses scraping dan menyimpan progres setiap **200 artikel**.

### Alasan
Scraping artikel merupakan proses yang panjang dan dapat terhenti karena error, koneksi, atau penghentian manual.

Checkpoint memungkinkan:
- proses dihentikan tanpa kehilangan seluruh progres;
- proses dilanjutkan tanpa mengulang artikel yang sudah selesai;
- hasil scraping dipulihkan dari checkpoint sebelumnya.

### Keputusan Tambahan
URL yang sudah selesai diproses dibaca kembali dari seluruh file checkpoint untuk menentukan artikel yang masih harus diproses.

---

## 8. Pemisahan Folder Checkpoint Produksi dan Validasi

### Keputusan
Eksperimen validasi menggunakan folder checkpoint yang terpisah dari proses produksi.

### Alasan
Pada akhir proses, seluruh file checkpoint dalam folder yang dirujuk akan digabungkan. Jika validasi menggunakan folder produksi, hasil scraping sebelumnya dapat ikut masuk ke dataset validasi.

### Parameter Isolasi
Tiga parameter disediakan:

- `--index-file`
- `--out-csv`
- `--ckpt-dir`

Keputusan ini memastikan eksperimen validasi dapat dijalankan tanpa mencemari hasil produksi.

---

## 9. Tidak Menggunakan `--limit-articles` untuk Validasi

### Keputusan
Parameter `--limit-articles` tidak digunakan untuk mengambil sampel validasi.

### Alasan
Parameter tersebut mengurutkan artikel berdasarkan `title_score` dan mengambil artikel dengan skor tertinggi.

Cara tersebut dapat menyebabkan sampel validasi terlalu banyak berisi artikel yang memiliki keyword geopolitik pada judul, sehingga tidak merepresentasikan populasi artikel secara keseluruhan.

### Keputusan Sampling Validasi
Sampel validasi menggunakan **random sampling terstratifikasi berdasarkan tahun**.

---

## 10. Stratified Sampling Berdasarkan Tahun

### Keputusan
Validasi konten menggunakan **210 artikel**, yaitu:

- 35 artikel per tahun
- 6 tahun
- 2021–2026
- `random_state=42`

### Alasan
Distribusi artikel dapat berbeda antar tahun. Stratifikasi memastikan setiap tahun dalam rentang penelitian tetap terwakili.

### Hasil
Sampling terstratifikasi menghasilkan tingkat keberhasilan fetch sebesar **93,4%**.

---

## 11. Penanganan Artikel Berbayar

### Keputusan
Artikel CNBC Pro dan Investing Club dikeluarkan dari korpus.

### Alasan
Konten berbayar tidak dapat diperoleh secara konsisten melalui scraping biasa.

URL artikel berbayar juga tidak selalu dapat dibedakan secara langsung dari artikel reguler.

### Sinyal yang Digunakan
Metadata `section` digunakan dengan kondisi yang mendeteksi:

- `pro:`
- `investing club`

Sinyal tersebut digunakan sebagai indikator utama artikel berbayar.

---

## 12. Penanganan Live Blog

### Keputusan
Artikel **live blog tidak dibuang** dari korpus.

### Alasan
Live blog tetap dapat mengandung informasi geopolitik yang relevan.

Selain itu, pipeline preprocessing menyediakan `description` sebagai fallback ketika `body` tidak tersedia. Dengan demikian, artikel live blog masih dapat menyediakan informasi teks yang dapat diproses.

### Indikator Live Blog
Deteksi menggunakan indikator seperti:

- tanda `;` pada judul;
- frasa seperti `"live updates"`.

---

## 13. Penanganan Zona Waktu

### Keputusan
Konversi zona waktu hanya dilakukan pada timestamp berita CNBC.

`published_utc` dikonversi menjadi `published_wib` menggunakan zona waktu:

`Asia/Jakarta`

### Alasan
Timestamp CNBC tersedia dalam UTC, sedangkan JISDOR berkaitan dengan waktu operasional pasar Indonesia.

JISDOR tidak dikonversi dari UTC karena data tersebut merepresentasikan tanggal perdagangan BI, bukan timestamp berita yang perlu dikonversikan.

---

## 14. Penentuan Cutoff Berita terhadap JISDOR

### Keputusan
Menggunakan **08:00 WIB** sebagai cutoff pembentukan target.

### Aturan
- Berita sebelum **08:00 WIB** → dapat dikaitkan dengan fixing pada hari tersebut.
- Berita pada atau setelah **08:00 WIB** → digulirkan ke fixing hari kerja BI berikutnya.

### Alasan
JISDOR dihitung berdasarkan transaksi antarbank pada sekitar **08:00–09:45 WIB** dan dipublikasikan sekitar pukul 10:00 WIB.

Cutoff 08:00 dipilih agar berita yang muncul setelah awal jendela pembentukan fixing tidak dianggap sebagai informasi yang memengaruhi harga yang sudah mulai terbentuk.

### Alternatif yang Tidak Dipilih
Menggunakan pukul 10:00 WIB sebagai cutoff.

### Alasan Tidak Dipilih
Berita pada pukul 09:30 WIB, misalnya, memang terbit sebelum JISDOR dipublikasikan, tetapi informasi tersebut sudah muncul ketika transaksi yang membentuk fixing sedang berlangsung.

---

## 15. Penanganan Berita di Luar Hari Perdagangan

### Keputusan
Menggunakan **roll-forward** ke hari kerja BI berikutnya.

### Contoh
Berita yang diterbitkan pada Sabtu atau Minggu akan dikaitkan dengan fixing hari kerja berikutnya.

### Alasan
Informasi tidak seharusnya dikaitkan dengan fixing yang sudah terjadi pada masa lalu.

### Alternatif yang Dipertimbangkan

#### Roll-backward
Tidak digunakan karena dapat menyebabkan informasi masa depan dikaitkan dengan harga yang sudah terbentuk.

#### Membuang berita akhir pekan
Tidak digunakan karena dapat menghilangkan informasi geopolitik penting yang terjadi ketika pasar sedang tutup.

---

## 16. Penentuan Kalender Hari Kerja

### Keputusan
Kalender hari kerja diturunkan langsung dari data JISDOR.

### Alasan
JISDOR hanya memiliki data pada hari ketika fixing tersedia. Dengan demikian, hari tanpa entri JISDOR dapat digunakan untuk mengidentifikasi hari non-trading tanpa bergantung pada library kalender eksternal.

---

## 17. Mempertahankan Hari Tanpa Berita

### Keputusan
Hari kerja yang tidak memiliki berita geopolitik **tetap dipertahankan** dalam `aligned_daily.csv`.

### Representasi
- `n_news = 0`
- `text_norm_concat = ""`

### Alasan
Tidak adanya berita merupakan kondisi yang memiliki makna dalam deret waktu.

Menghapus hari tanpa berita dapat menyebabkan:
- kontinuitas deret waktu terganggu;
- observasi kurs hilang;
- model hanya melihat hari yang memiliki berita.

---

## 18. Normalisasi Volume Berita

### Keputusan
Tidak menggunakan `n_news` mentah sebagai satu-satunya ukuran volume berita.

Variabel tambahan:

`news_density = n_news / window_hours`

digunakan untuk mempertimbangkan perbedaan panjang jendela waktu.

### Alasan
Jendela berita untuk hari Senin lebih panjang karena mencakup periode akhir pekan.

Rata-rata:

- Senin: sekitar **62,85 jam**
- Hari kerja lainnya: sekitar **30 jam**

Namun jumlah berita tidak meningkat dua kali lipat. Hal ini menunjukkan bahwa jumlah berita mentah tidak dapat dibandingkan langsung antar hari tanpa memperhitungkan panjang jendela.

### Implikasi
`n_news / window_hours` dapat digunakan sebagai variabel kontrol dalam pemodelan atau analisis deskriptif.

---

## 19. Jalur Preprocessing TF-IDF dan BERT

### Keputusan
Membuat dua jalur preprocessing yang berbeda:

1. **TF-IDF**
2. **FinBERT/BERT**

### Alasan
Kedua jenis representasi teks memiliki kebutuhan preprocessing yang berbeda.

TF-IDF bekerja pada token yang telah dinormalisasi, sedangkan tokenizer BERT membutuhkan bentuk teks yang relatif alami agar proses subword tokenization tetap bekerja sebagaimana mestinya.

---

## 20. Preprocessing TF-IDF

### Keputusan
Pada jalur TF-IDF:

- melakukan lowercase;
- menghapus sebagian besar tanda baca;
- mempertahankan `.`, `$`, dan `%`;
- menggunakan custom stopword;
- mempertahankan kata negasi;
- tidak melakukan stemming;
- tidak melakukan lemmatization;
- melakukan deduplikasi;
- menghapus data yang bukan artikel valid.

### Alasan

#### Mempertahankan `$` dan `%`
Simbol tersebut dapat menunjukkan informasi ekonomi, misalnya:

- `oil surges 8%`
- `$100 billion in sanctions`

#### Mempertahankan `.`
Diperlukan untuk:
- angka desimal seperti `3.5`;
- singkatan seperti `U.S.`

#### Mempertahankan Negasi
Kata seperti:

- `not`
- `no`
- `never`
- `without`

dipertahankan karena penghapusannya dapat mengubah makna kalimat.

#### Tidak Melakukan Stemming
Stemming dapat menghasilkan bentuk kata yang tidak bermakna pada nama negara, organisasi, atau istilah geopolitik.

---

## 21. Preprocessing BERT

### Keputusan
Melakukan preprocessing seminimal mungkin pada teks yang akan diberikan kepada FinBERT.

### Keputusan
Tidak melakukan:

- lowercase manual;
- penghapusan tanda baca secara agresif;
- stopword removal;
- stemming;
- lemmatization.

### Alasan
Tokenizer BERT dirancang untuk memproses teks dalam bentuk yang relatif alami. Normalisasi agresif dapat mengubah representasi teks yang diharapkan oleh model pretrained.

---

## 22. Penghapusan Boilerplate pada BERT

### Keputusan
Menghapus boilerplate CNBC yang telah diuji sebelumnya, tetapi tidak melakukan penghapusan teks secara agresif.

### Contoh
Boilerplate yang dapat dihapus adalah bagian berulang seperti promosi atau footer tertentu.

### Alasan
Teks boilerplate tidak merepresentasikan informasi geopolitik dan dapat menjadi noise bagi model.

### Keputusan Tambahan
Pola boilerplate harus diuji terhadap keseluruhan korpus sebelum digunakan agar kalimat berita asli tidak ikut terhapus.

---

## 23. Penanganan Artikel Tanpa Body

### Keputusan
Jika body artikel tidak tersedia, menggunakan `description` sebagai fallback.

### Alasan
Sebagian artikel, terutama artikel dengan format live blog, tidak memiliki body yang dapat diekstraksi secara normal.

Sebanyak **454 artikel** menggunakan description sebagai fallback.

---

## 24. Penanganan Panjang Teks BERT

### Keputusan
Artikel yang melebihi kapasitas BERT diproses menggunakan **chunking 512 token dengan overlap 50 token**.

### Alasan
BERT memiliki batas panjang input sekitar 512 token.

Rata-rata artikel setelah preprocessing sekitar **710 token**, dan sekitar **73,4% artikel** melebihi batas tersebut.

### Alasan Menggunakan Overlap
Overlap 50 token digunakan untuk mengurangi risiko informasi penting terpotong tepat pada batas antar-chunk.

---

## 25. Pemrosesan Data Kurs JISDOR

### Keputusan
Data JISDOR dibersihkan dan diubah menjadi format kronologis dari tanggal terlama ke tanggal terbaru.

### Alasan
Data raw JISDOR tersusun dari tanggal terbaru ke tanggal terlama, sedangkan perhitungan perubahan nilai tukar membutuhkan informasi hari sebelumnya.

---

## 26. Parsing Format Tanggal JISDOR

### Keputusan
Format tanggal JISDOR dibaca secara eksplisit sebagai `M/D/YYYY` dan dikonversi menjadi `YYYY-MM-DD`.

### Alasan
Parsing eksplisit menghindari ambiguitas antara format bulan/hari dan hari/bulan.

Format standar `YYYY-MM-DD` juga memudahkan pengurutan berdasarkan waktu.

---

## 27. Parsing Nilai Kurs

### Keputusan
Parser kurs dibuat untuk menangani format angka Indonesia maupun Inggris.

### Contoh
- `15.250,00`
- `15,250.00`

### Alasan
Perbedaan pemisah ribuan dan desimal dapat menyebabkan nilai kurs terbaca secara salah apabila format tidak ditangani secara eksplisit.

---

## 28. Penghapusan Kolom NO JISDOR

### Keputusan
Kolom `NO` dihapus setelah data dibaca.

### Alasan
Kolom tersebut hanya merupakan nomor urut dan tidak memiliki informasi ekonomi yang digunakan dalam pemodelan.

---

## 29. Pembentukan Target Kurs

### Keputusan
Perubahan kurs dibandingkan dengan **hari kerja BI sebelumnya**, bukan tanggal kalender sebelumnya.

### Alasan
JISDOR tidak tersedia pada:
- Sabtu;
- Minggu;
- hari libur;
- cuti bersama.

Dengan menggunakan hari kerja BI sebelumnya, perubahan kurs Senin dibandingkan dengan Jumat sebelumnya, bukan Minggu.

---

## 30. Menyimpan Variabel Kontrol Alignment

### Keputusan
Menyimpan variabel kontrol berikut pada `aligned_daily.csv`:

- `is_offhours`
- `hours_to_fixing`
- `window_hours`
- `n_news`
- `target_date_lag1`

### Alasan
Variabel tersebut memungkinkan proses temporal alignment diperiksa dan digunakan dalam analisis robustness.

Keputusan ini mencegah efek dari perbedaan panjang jendela waktu tersembunyi di dalam dataset.

---

## 31. Mempertahankan Varian Lag-1

### Keputusan
`target_date_lag1` disimpan sebagai varian target untuk robustness check.

### Alasan
Variabel ini memungkinkan pengujian alternatif terhadap aturan alignment utama tanpa perlu mengulang seluruh proses akuisisi dan preprocessing.

---

## 32. Struktur Dataset Akhir

### Keputusan
Hasil temporal alignment disimpan dalam:

`aligned_daily.csv`

### Alasan
File ini menjadi titik pertemuan antara:

- representasi berita geopolitik;
- informasi tanggal;
- jumlah berita;
- informasi jendela waktu;
- nilai tukar;
- target perubahan kurs.

Dengan demikian, tahap pemodelan dapat dilakukan menggunakan dataset yang sudah terstruktur secara temporal.

---

## 33. Target Prediksi: Kelas Volatilitas

### Keputusan
Target model adalah `volatility_class` (`low` / `medium` / `high`), yaitu kelas dari `realized_vol`:

`realized_vol(t) = std(log_return[t-4], ..., log_return[t])`

atau simpangan baku perubahan kurs (log return) selama 5 hari kerja BI terakhir, termasuk hari t (`VOLATILITY_WINDOW = 5`).

### Alasan
- Pertanyaan penelitian berfokus pada **fluktuasi** nilai tukar, bukan arah naik/turun. Volatilitas lebih relevan untuk menangkap dampak ketidakpastian geopolitik.
- Jendela 5 hari kerja (±1 minggu) meredam derau harian satu hari.

### Konsekuensi yang Perlu Dipahami
Jendela hari t dan hari t-1 berbagi 4 dari 5 return yang sama, sehingga kelas volatilitas sangat persisten dari hari ke hari. Akibatnya baseline naive persistence (Keputusan 36) sudah kuat, dan fitur harga perlu dirancang mengikuti struktur ini (Keputusan 37).

### Alternatif yang Dipertimbangkan
- Arah perubahan kurs (`direction`: up/flat/down dengan `FLAT_THRESHOLD`).
- Volatilitas ke depan yang tidak tumpang tindih dengan data kemarin (mis. |r[t]| atau std r[t..t+4]).

### Alasan Tidak Dipilih
Kolom `direction` tetap dihitung di `preprocess_kurs.py`, tetapi tidak dipakai sebagai target karena pertanyaan penelitian adalah fluktuasi. Target volatilitas ke depan tidak dipilih untuk menjaga definisi target yang sudah ditetapkan; keterbatasan persistensinya dicatat sebagai bagian dari interpretasi hasil.

---

## 34. Ambang Kelas Volatilitas (Tertile dari Data Train)

### Keputusan
`realized_vol` dibagi menjadi 3 kelas menggunakan **tertile** (`pd.qcut(..., 3)`) yang dihitung **hanya dari 70% hari kerja tertua**. Ambang yang diperoleh:

- `low`: realized_vol < 0,207%
- `medium`: 0,207% – 0,312%
- `high`: > 0,312%

Ambang yang sama kemudian diterapkan (`pd.cut`) ke seluruh deret, termasuk valid dan test.

### Alasan
- **Kelas seimbang:** tertile membagi data train menjadi tiga kelompok berukuran sama, sehingga model tidak bisa mendapat akurasi tinggi hanya dengan menebak satu kelas.
- **Relatif terhadap perilaku rupiah:** "high" berarti lebih bergejolak dari kebiasaan USD/IDR selama periode train, bukan ambang absolut yang dipilih manual.
- **Mencegah kebocoran:** jika ambang dihitung dari seluruh data, ambang tersebut ikut "mengetahui" sebaran volatilitas periode test.

### Konsekuensi
Distribusi kelas di valid dan test tidak lagi seimbang (test: low 51, medium 65, high 51). Hal ini wajar karena kondisi pasar berubah antar periode.

---

## 35. Split Kronologis 70/15/15 pada Hari Berberita

### Keputusan
- Pelabelan kelas dan fitur lag dihitung pada **kalender hari kerja lengkap**, baru kemudian difilter ke hari yang memiliki berita (`n_news > 0`).
- Data dibagi secara kronologis: 70% train, 15% valid, 15% test.
- Ketiga skrip training (`train_baseline_ts.py`, `train_tfidf.py`, `train_combined.py`) memakai **himpunan hari yang identik**:
  - Train: 772 hari (16-09-2021 s.d. 25-03-2025)
  - Valid: 165 hari (26-03-2025 s.d. 09-12-2025)
  - Test: 167 hari (11-12-2025 s.d. 01-09-2026)

### Alasan
- Split acak akan membuat model belajar dari masa depan untuk memprediksi masa lalu.
- Valid dipakai untuk memilih hyperparameter; test hanya dipakai **satu kali** di akhir.
- Fitur lag dihitung sebelum filter agar "hari sebelumnya" selalu berarti hari kerja BI sebelumnya, bukan hari berberita sebelumnya.
- Himpunan hari yang identik diperlukan agar akurasi antar model dapat dibandingkan secara langsung.

---

## 36. Baseline Naive Persistence

### Keputusan
Baseline utama adalah **naive persistence**: kelas volatilitas hari t diprediksi sama dengan kelas hari t-1 (`lag1_volatility_class`). Baseline ini tidak dilatih dan tidak memiliki hyperparameter.

### Alasan
Karena target sangat persisten (Keputusan 33), naive persistence adalah tolok ukur minimum yang bermakna. Model yang tidak dapat melampaui naive tidak memberikan nilai tambah.

### Alternatif yang Tidak Dipilih
Dummy classifier (selalu menebak kelas mayoritas train). Baseline ini dihapus karena terlalu lemah (akurasi test 0,305, setara menebak acak) dan tidak relevan untuk pertanyaan penelitian.

---

## 37. Fitur Harga (`PRICE_FEATURES`)

### Keputusan
Fitur harga didefinisikan satu kali di `dataset_split.py` dan dipakai **sama persis** oleh XGBoost tanpa NLP dan XGBoost + TF-IDF + LM:

| Fitur | Isi |
|---|---|
| `lag1_log_return` s.d. `lag4_log_return` | Return 1–4 hari kerja sebelumnya |
| `known4_mean`, `known4_std` | Rata-rata dan simpangan baku dari r[t-4..t-1] |
| `vol_if_r0` | `realized_vol(t)` jika r[t] = 0 |
| `vol_if_rtyp_pos`, `vol_if_rtyp_neg` | `realized_vol(t)` jika r[t] = ± median \|r\| historis (expanding, di-shift 1 hari) |
| `lag1_volatility_class_enc` | Kelas kemarin (low = 0, medium = 1, high = 2) |

### Alasan
Empat dari lima return dalam jendela target sudah diketahui sebelum hari t (Keputusan 33). Fitur di atas memberikan informasi tersebut secara langsung, sehingga model cukup menilai apakah pergerakan hari t (dan informasi berita) cukup besar untuk memindahkan kelas.

Semua fitur hanya menggunakan data **sebelum hari t**. Hal ini telah diuji: mengubah return hari t dan sesudahnya tidak mengubah nilai fitur hari t.

### Alternatif yang Dipertimbangkan
Fitur awal: `lag1–3_log_return`, `lag1_realized_vol`, `lag1_volatility_class_enc`.

### Alasan Tidak Dipilih
- `lag4_log_return` tidak tersedia, padahal r[t-4] masih termasuk dalam jendela target.
- `lag1_realized_vol` memuat r[t-5], yaitu return yang sudah keluar dari jendela target.
- Dengan fitur awal, XGBoost tanpa NLP hanya mencapai akurasi test 0,689, lebih rendah dari naive (0,713).

---

## 38. Tipe Numerik untuk Fitur Kelas Kemarin

### Keputusan
`lag1_volatility_class_enc` disimpan sebagai **float** (`.astype(float)`).

### Alasan
Tanpa konversi, kolom tersebut mewarisi tipe `category` dari `pd.cut`. XGBoost membacanya sebagai kategori tanpa urutan jika diberi DataFrame (XGBoost tanpa NLP dan ablasi), tetapi sebagai angka berurutan jika diberi array numpy (model gabungan). Akibatnya fitur yang sama diperlakukan berbeda antar model yang dibandingkan. Pada versi XGBoost lama, kondisi ini juga dapat menimbulkan error.

---

## 39. Normalisasi Fitur Sentimen LM (Rata-rata per Artikel)

### Keputusan
Fitur sentimen Loughran-McDonald yang dipakai model:

- `mean_lm_polarity`
- `lm_positive_mean = lm_positive_sum / n_news`
- `lm_negative_mean = lm_negative_sum / n_news`

Fitur ini didefinisikan sekali sebagai `LM_FEATURES` di `dataset_split.py`.

### Alasan
- **Konsisten dengan Keputusan 18.** Jumlah berita mentah tidak dapat dibandingkan langsung antar hari. Fitur berbasis jumlah (`lm_*_sum`) memiliki masalah yang sama karena nilainya ikut membesar seiring jumlah artikel.
- **Fitur sentimen seharusnya mengukur nada, bukan volume.** Volume berita sudah terwakili terpisah melalui `n_news`.
- **Temuan EDA:** jumlah artikel per hari tidak stabil antar periode (rata-rata 3,9 pada train dan 8,0 pada valid), diduga akibat perbedaan cakupan scraping. Sementara itu, jumlah kata negatif per artikel relatif stabil (±21–27). Pergeseran ini sudah terlihat pada train dan valid, tanpa perlu melihat data test.

### Alternatif yang Dipertimbangkan
`lm_positive_sum` dan `lm_negative_sum` (jumlah per hari).

### Catatan Transparansi
Kedua versi telah dibandingkan. Akurasi test model utama identik (0,766) untuk kedua versi, sehingga keputusan ini tidak mengubah kesimpulan dan tidak didasarkan pada hasil test.

---

## 40. Representasi TF-IDF pada Model Gabungan

### Keputusan
- TF-IDF: `min_df=5`, `max_df=0.8`, unigram + bigram, maksimum 5.000 fitur, di-fit dari data train saja.
- Untuk model gabungan, TF-IDF dikompres menjadi 20 komponen dengan `TruncatedSVD` yang juga di-fit dari data train saja.

### Alasan
Tanpa kompresi, 5.000 kolom TF-IDF akan mendominasi pemilihan split pada pohon XGBoost, sehingga fitur harga dan LM yang jumlahnya jauh lebih sedikit hampir tidak pernah terpakai. Model TF-IDF saja (`train_tfidf.py`) tetap memakai 5.000 kolom penuh karena tidak digabung dengan fitur lain.

---

## 41. XGBoost dengan Tuning Hyperparameter yang Seragam

### Keputusan
Semua model XGBoost di-tuning menggunakan fungsi dan grid yang sama (`tune_xgb` dan `XGB_GRID` di `dataset_split.py`):

- `n_estimators`: 100, 200, 400
- `max_depth`: 2, 3, 4
- `learning_rate`: 0,03; 0,05; 0,1

Total 27 kombinasi. Setiap kombinasi dilatih pada train dan dinilai dengan akurasi valid. Kombinasi terbaik dievaluasi pada test **satu kali**. Parameter lain memakai default XGBoost dengan `random_state=42`.

### Alasan
- Sebelumnya hanya model gabungan yang di-tuning, sedangkan model pembanding memakai parameter tetap. Perbandingan seperti itu tidak adil karena model NLP mendapat kesempatan optimasi lebih banyak.
- Dengan grid yang sama, selisih akurasi antar model mencerminkan kontribusi fitur, bukan perbedaan upaya tuning.

### Alternatif yang Tidak Dipilih
Logistic Regression sebagai algoritma pembanding pada model teks saja. Algoritma ini dihapus karena perbandingan antar algoritma bukan bagian dari pertanyaan penelitian.

---

## 42. Model yang Dibandingkan

### Keputusan
**Perbandingan utama** (`train_combined.py`):

1. Naive persistence (baseline)
2. XGBoost tanpa NLP (`PRICE_FEATURES`)
3. XGBoost + TF-IDF + LM (model utama)

**Pendukung:**

- XGBoost teks saja: TF-IDF saja dan LM saja, tanpa fitur harga (`train_tfidf.py`).
- Ablasi: XGBoost harga + LM tanpa TF-IDF (`train_combined.py`).

### Alasan
- Selisih (3) terhadap (2) mengukur kontribusi berita geopolitik di atas histori harga, yang merupakan inti pertanyaan penelitian.
- Model teks saja menguji apakah berita dapat memprediksi volatilitas **tanpa** histori harga.
- Ablasi memisahkan kontribusi LM dari TF-IDF.

---

## 43. Metrik Evaluasi dan Uji Signifikansi

### Keputusan
- Metrik utama: **akurasi** pada test set. Metrik pendukung: macro F1, classification report, dan confusion matrix.
- Signifikansi selisih antar model diuji dengan **uji McNemar exact** (α = 0,05) pada test set. Uji ini sudah dijalankan otomatis di `train_combined.py`.

### Alasan
- Kelas pada data train seimbang, sehingga akurasi mudah diinterpretasikan. Macro F1 ditambahkan karena distribusi kelas test tidak seimbang.
- Uji McNemar sesuai untuk membandingkan dua classifier pada data uji yang sama: yang dihitung hanya hari-hari ketika kedua model memberikan hasil berbeda.

---

## 44. Hasil Evaluasi Akhir dan Keterbatasan

### Hasil (test set, 167 hari)

| Model | Akurasi valid | Akurasi test | Macro F1 test |
|---|---|---|---|
| Naive persistence | 0,727 | 0,713 | 0,72 |
| XGBoost teks saja (TF-IDF) | 0,388 | 0,287 | 0,20 |
| XGBoost teks saja (LM) | 0,370 | 0,305 | 0,31 |
| XGBoost tanpa NLP | 0,806 | 0,731 | 0,74 |
| Ablasi: harga + LM | 0,818 | 0,737 | – |
| **XGBoost + TF-IDF + LM** | **0,812** | **0,766** | **0,77** |

Uji McNemar (hari "A saja benar" / "B saja benar"):

- XGBoost tanpa NLP vs naive: 20 / 17, p = 0,743
- XGBoost + TF-IDF + LM vs XGBoost tanpa NLP: 9 / 3, p = 0,146
- XGBoost + TF-IDF + LM vs naive: 23 / 14, p = 0,188

### Interpretasi
- Histori harga merupakan sumber informasi utama. Total feature importance model utama: harga 0,69, TF-IDF 0,26, LM 0,06.
- Berita geopolitik menambah akurasi sebesar +3,6 poin di atas model harga saja, terutama pada kelas `medium`. Namun peningkatan ini **tidak signifikan secara statistik** pada α = 0,05.
- Berita **tidak mampu memprediksi sendirian**. Model teks saja berada pada tingkat tebakan acak, dan model TF-IDF saja cenderung menghafal kosakata periode tertentu (misalnya "invasion", "annexation crimea") alih-alih pola yang dapat digeneralisasi.
- TF-IDF (topik berita) lebih informatif dibanding nada sentimen LM.

### Keterbatasan
- Test set kecil (167 hari): satu hari setara 0,6 poin akurasi.
- Evaluasi hanya pada satu periode test.
- Jumlah artikel per hari meningkat pada 2025–2026, kemungkinan akibat cakupan scraping.
- Fitur harga (Keputusan 37) dirancang pada tahap eksplorasi ketika hasil test versi awal sudah terlihat. Rancangannya diturunkan dari definisi target, bukan dari coba-coba, tetapi hal ini tetap dicatat sebagai keterbatasan.

---

# Ringkasan Keputusan Utama

| No. | Aspek | Keputusan |
|---|---|---|
| 1 | Sumber berita | CNBC |
| 2 | Sumber kurs | JISDOR Bank Indonesia |
| 3 | Akuisisi archive | Playwright |
| 4 | Filtering awal | Lexicon-based title filtering |
| 5 | Ekstraksi utama | JSON-LD |
| 6 | Ekstraksi fallback | Meta tag → CSS selector |
| 7 | Validasi CSS | Minimal 3 paragraf |
| 8 | Checkpoint | Setiap 200 artikel |
| 9 | Validasi scraping | Stratified random sampling |
| 10 | Artikel berbayar | Dikeluarkan |
| 11 | Live blog | Dipertahankan |
| 12 | Zona waktu berita | UTC → WIB |
| 13 | Cutoff | 08:00 WIB |
| 14 | Non-trading day | Roll-forward |
| 15 | Hari tanpa berita | Dipertahankan |
| 16 | Volume berita | Dinormalisasi terhadap `window_hours` |
| 17 | Representasi teks | TF-IDF + FinBERT |
| 18 | TF-IDF preprocessing | Normalisasi lebih agresif |
| 19 | BERT preprocessing | Minimal |
| 20 | BERT long text | Chunk 512 + overlap 50 |
| 21 | Missing body | Description fallback |
| 22 | Target kurs | Dibandingkan dengan hari kerja BI sebelumnya |
| 23 | Kalender trading | Diturunkan dari JISDOR |
| 24 | Dataset alignment | `aligned_daily.csv` |
| 25 | Robustness | `target_date_lag1` |
| 26 | Target model | `volatility_class` dari realized_vol 5 hari kerja |
| 27 | Ambang kelas | Tertile dari data train (0,207% / 0,312%) |
| 28 | Split | Kronologis 70/15/15, hari identik di semua skrip |
| 29 | Baseline | Naive persistence (dummy dihapus) |
| 30 | Fitur harga | `PRICE_FEATURES` (4 return terakhir + skenario `vol_if_*`) |
| 31 | Tipe fitur kelas kemarin | Numerik (float) |
| 32 | Fitur sentimen | LM rata-rata per artikel |
| 33 | TF-IDF pada model gabungan | Dikompres `TruncatedSVD` 20 komponen |
| 34 | Algoritma & tuning | XGBoost, grid 27 kombinasi yang sama via akurasi valid |
| 35 | Perbandingan utama | Naive vs XGBoost tanpa NLP vs XGBoost + TF-IDF + LM |
| 36 | Evaluasi | Akurasi, macro F1, uji McNemar |