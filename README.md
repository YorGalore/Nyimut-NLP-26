# Prediksi Peristiwa Geopolitik Global: Menganalisis Dampak Terhadap Nilai Tukar Dolar

**Mata Kuliah:** Pemrosesan Bahasa Alami
**Tim:** Nyimut

**Anggota:**

* Adzrha Auryn Alius — `24/533582/PA/22594`
* Aliya Khairun Nisa — `24/543832/PA/23111`
* Freta Yordinia Laura — `24/533444/PA/22576`
* Jessy Marcia Anabel — `24/538431/PA/22846`

---

## Tentang Proyek

Proyek ini bertujuan untuk menganalisis apakah **informasi dari berita geopolitik global dapat digunakan untuk memprediksi perubahan nilai tukar USD/IDR**. Data berita diperoleh dari **CNBC**, sedangkan data nilai tukar diperoleh dari **JISDOR (Jakarta Interbank Spot Dollar Rate)** yang diterbitkan oleh Bank Indonesia. Nantinya, proyek akan mengembangkan dua jalur pemrosesan teks:

* **TF-IDF** sebagai representasi teks berbasis metode klasik.
* **FinBERT** sebagai representasi teks berbasis Transformer.

Kedua representasi tersebut kemudian digunakan sebagai bagian dari pipeline analisis hubungan antara peristiwa geopolitik dan perubahan nilai tukar.

---

## Dataset

### 1. CNBC

Data berita geopolitik diperoleh dari halaman archive CNBC untuk periode penelitian. Informasi yang dikumpulkan meliputi:

* Judul artikel
* URL artikel
* Tanggal publikasi
* Deskripsi
* Isi artikel
* Penulis
* Section artikel

### 2. JISDOR

Data nilai tukar diperoleh dari **JISDOR (Jakarta Interbank Spot Dollar Rate)** Bank Indonesia. Data digunakan untuk memperoleh:
* Tanggal perdagangan
* Nilai kurs USD/IDR
* Kurs hari kerja sebelumnya
* Perubahan nilai tukar sebagai target prediksi

Periode data:

```text
1 September 2021 – 1 September 2026
```

---

## Tech Stack

### Programming Language

* **Python 3.10+**

### Data Processing

* **Pandas**
* **NumPy**

### Web Scraping

* **Playwright**
* **BeautifulSoup4**
* **Requests**

### Natural Language Processing

* **NLTK**
* **Hugging Face Transformers**
* **FinBERT**
* **scikit-learn**

### Machine Learning

* **scikit-learn**
* TF-IDF

### Development Environment

* **Git & GitHub**
* **Visual Studio Code**
* Python Virtual Environment (`venv`)

---

## Instalasi

### 1. Clone Repository

```bash
git clone <URL_REPOSITORY>
cd Nyimut-NLP-26
```

### 2. Membuat Virtual Environment

Disarankan menggunakan virtual environment agar dependency proyek terisolasi dari instalasi Python sistem.

```bash
python3 -m venv .venv
```

Aktifkan virtual environment:

**macOS / Linux**

```bash
source .venv/bin/activate
```

**Windows**

```bash
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Browser Playwright

Jika menjalankan proses scraping CNBC:

```bash
playwright install chromium
```

---

## Dokumentasi

Dokumentasi proyek tersedia pada folder `docs/`. Beberapa dokumentasi utama:

* [`Keputusan.md`](docs/Keputusan.md) — dokumentasi keputusan metodologis dan teknis proyek.
* Laporan proyek — penjelasan lengkap mengenai metodologi, preprocessing, akuisisi data, dan temporal alignment.

---

**Mata Kuliah:** Pemrosesan Bahasa Alami
**Departemen Ilmu Komputer dan Elektronika**
**Fakultas Matematika dan Ilmu Pengetahuan Alam**
**Universitas Gadjah Mada**
**2026**
