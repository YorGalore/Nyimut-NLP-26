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