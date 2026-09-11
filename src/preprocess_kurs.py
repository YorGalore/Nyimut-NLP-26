"""
preprocess_kurs.py
==================
Membersihkan data kurs JISDOR dari Bank Indonesia.
data/raw/jisdor_raw.csv -> data/processed/kurs_clean.csv

DUA JEBAKAN YANG DITANGANI DI SINI
----------------------------------

JEBAKAN 1 -- Format angka Indonesia.
BI menulis nilai sebagai "15.250,00" (titik = pemisah ribuan, koma = desimal).
pandas akan membacanya sebagai string, atau lebih buruk, salah mengurai
menjadi 15.25. Ditangani eksplisit di clean_number().

JEBAKAN 2 -- JANGAN mengisi hari yang hilang.
Godaannya adalah reindex ke kalender harian lalu forward-fill supaya "rapi".
JANGAN. Hari tanpa JISDOR adalah hari tanpa fixing -- dan fakta itu justru
INTI dari tugas penyelarasan temporal. Forward-fill menciptakan hari libur
dengan return 0% yang akan dipelajari model sebagai pola palsu.

KONSEKUENSI POSITIFNYA:
Himpunan tanggal yang ADA di JISDOR = kalender hari kerja Bank Indonesia.
Akhir pekan, libur nasional, dan cuti bersama otomatis terdefinisi sebagai
"tanggal yang tidak ada di JISDOR". Kita tidak perlu library hari libur
sama sekali. Kalender diturunkan dari data itu sendiri.
"""

import re

import numpy as np
import pandas as pd

import config as C


# Nama bulan Indonesia -> nomor. BI kadang mengekspor "01 September 2021".
BULAN_ID = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10,
    "november": 11, "desember": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "agu": 8, "ags": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
}


def clean_number(value):
    """
    "15.250,00" -> 15250.0
    "15,250.00" -> 15250.0
    15250.0     -> 15250.0

    Logikanya: kalau ada koma DAN titik, yang muncul terakhir adalah
    pemisah desimal. Kalau hanya ada satu jenis, kita tebak dari posisinya.
    """
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip().replace(" ", "")
    s = re.sub(r"[^\d.,\-]", "", s)
    if not s:
        return np.nan

    has_dot, has_comma = "." in s, "," in s

    if has_dot and has_comma:
        if s.rfind(",") > s.rfind("."):      # format Indonesia: 15.250,00
            s = s.replace(".", "").replace(",", ".")
        else:                                 # format Inggris: 15,250.00
            s = s.replace(",", "")
    elif has_comma:
        # Koma sendirian. Kalau tepat 3 digit di belakangnya -> pemisah ribuan.
        s = s.replace(",", "" if re.search(r",\d{3}$", s) else ".")
    elif has_dot:
        # Titik sendirian. Kalau tepat 3 digit di belakangnya -> pemisah ribuan.
        # (Kurs USD/IDR selalu 5 digit, jadi "15.250" pasti ribuan, bukan desimal.)
        if re.search(r"\.\d{3}$", s):
            s = s.replace(".", "")

    try:
        return float(s)
    except ValueError:
        return np.nan


def parse_date(value):
    """Tangani beberapa kemungkinan format tanggal dari ekspor BI."""
    if pd.isna(value):
        return pd.NaT
    s = str(value).strip()

    # Format ISO "2021-09-01" HARUS dicek duluan.
    # Kalau tidak, dayfirst=True di bawah akan membacanya sebagai 9 Januari.
    # Ini bug halus yang ditemukan saat pengujian -- tanggal terurai tanpa
    # error, hanya salah, jadi tidak akan ketahuan sampai hasil alignment aneh.
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}", s):
        return pd.to_datetime(s, errors="coerce")

    # Format "01 September 2021" / "1 Sep 2021"
    m = re.match(r"^(\d{1,2})[\s\-/]+([A-Za-z]+)[\s\-/]+(\d{4})$", s)
    if m:
        day, mon_name, year = m.groups()
        mon = BULAN_ID.get(mon_name.lower())
        if mon:
            return pd.Timestamp(int(year), mon, int(day))

    # Format numerik: dayfirst=True karena BI memakai DD/MM/YYYY
    for kwargs in ({"dayfirst": True}, {"dayfirst": False}):
        ts = pd.to_datetime(s, errors="coerce", **kwargs)
        if pd.notna(ts):
            return ts
    return pd.NaT


def find_column(df, candidates):
    """Cari kolom berdasarkan potongan nama, tanpa peduli huruf besar/kecil."""
    for col in df.columns:
        low = str(col).lower().strip()
        if any(c in low for c in candidates):
            return col
    return None


def main():
    # BI kadang mengekspor dengan pemisah titik-koma dan beberapa baris header.
    # sep=None + engine="python" membuat pandas menebak pemisahnya sendiri.
    df = pd.read_csv(C.JISDOR_RAW_CSV, sep=None, engine="python", skip_blank_lines=True)
    print("Kolom terbaca:", list(df.columns))

    col_date = find_column(df, ["tanggal", "date"])
    col_rate = find_column(df, ["kurs", "nilai", "rate", "jisdor"])

    if col_date is None or col_rate is None:
        raise SystemExit(
            f"Kolom tidak terdeteksi otomatis. Kolom yang ada: {list(df.columns)}\n"
            "Perbaiki daftar kandidat di find_column(), atau rename kolom di CSV."
        )
    print(f"Kolom tanggal -> '{col_date}' | Kolom kurs -> '{col_rate}'")

    out = pd.DataFrame({
        "date": df[col_date].apply(parse_date),
        "kurs": df[col_rate].apply(clean_number),
    })

    before = len(out)
    out = out.dropna(subset=["date", "kurs"])
    out = out[out["kurs"] > 1000]   # sanity: USD/IDR tidak mungkin < 1000
    out = out.drop_duplicates(subset=["date"], keep="last").sort_values("date")

    # Batasi ke rentang tugas
    out = out[
        (out["date"] >= pd.Timestamp(C.START_DATE))
        & (out["date"] <= pd.Timestamp(C.END_DATE))
    ].reset_index(drop=True)

    # --- variabel target -----------------------------------------------------
    # PENTING: prev_kurs adalah fixing SEBELUMNYA, bukan kalender H-1.
    # Setelah libur Lebaran, prev_date bisa 8 hari sebelumnya. gap_days
    # disimpan supaya Tugas 2 bisa menormalisasi efek ini.
    out["prev_date"] = out["date"].shift(1)
    out["prev_kurs"] = out["kurs"].shift(1)
    out["gap_days"] = (out["date"] - out["prev_date"]).dt.days

    out["delta"] = out["kurs"] - out["prev_kurs"]
    out["log_return"] = np.log(out["kurs"] / out["prev_kurs"])

    # Label arah dengan zona mati. Pergerakan < FLAT_THRESHOLD dianggap noise;
    # memaksanya jadi naik/turun akan mengajari model membedakan yang acak.
    out["direction"] = np.select(
        [out["log_return"] > C.FLAT_THRESHOLD, out["log_return"] < -C.FLAT_THRESHOLD],
        ["up", "down"],
        default="flat",
    )

    out.to_csv(C.KURS_CLEAN_CSV, index=False)

    print("\nRINGKASAN KURS JISDOR")
    print("-" * 50)
    print(f"  Baris mentah              : {before:,}")
    print(f"  Baris valid dalam rentang : {len(out):,}")
    print(f"  Rentang tanggal           : {out['date'].min().date()} .. {out['date'].max().date()}")
    print(f"  Kurs min / maks           : {out['kurs'].min():,.0f} / {out['kurs'].max():,.0f}")
    print(f"  Gap terbesar antar fixing : {out['gap_days'].max():.0f} hari")
    print("\n  Distribusi label arah:")
    print(out["direction"].value_counts().to_string())
    print(f"\nTersimpan: {C.KURS_CLEAN_CSV}")


if __name__ == "__main__":
    main()