import pandas as pd

df = pd.read_csv("data/raw/cnbc_sampel_hasil.csv")
df["body_len"] = df["body"].fillna("").str.len()
df["kosong"] = df["body_len"] == 0

sec = df["section"].fillna("").str.lower()
df["paywall"] = sec.str.contains("pro:|investing club", regex=True)

judul = df["title"].fillna("").str.lower()
slug = df["url"].fillna("").str.lower()
pola = "live updates|live blog|war updates|live-updates|live-blog"
df["live"] = judul.str.contains(pola, regex=True) | slug.str.contains(pola, regex=True)

bisa = df[~df["paywall"]]

print("Total sampel        :", len(df))
print("Paywall (dibuang)   :", df["paywall"].sum())
print("Populasi valid      :", len(bisa))
print("Berhasil di-parse   :", (~bisa["kosong"]).sum())
print("Success rate efektif: {:.1%}".format((~bisa["kosong"]).mean()))
print()

th = pd.to_datetime(df["index_date"], errors="coerce").dt.year
ringkas = pd.DataFrame({
    "sampel": th.value_counts(),
    "paywall": th[df["paywall"]].value_counts(),
    "valid": th[~df["paywall"]].value_counts(),
    "gagal": th[~df["paywall"] & df["kosong"]].value_counts(),
}).sort_index().fillna(0).astype(int)
ringkas["rate"] = ((1 - ringkas["gagal"] / ringkas["valid"]) * 100).round(1)
print(ringkas.to_string())
print()

sisa = ~df["paywall"] & df["kosong"] & ~df["live"]
print("Gagal tanpa penjelasan:", sisa.sum())
if sisa.sum():
    print(df.loc[sisa, ["section", "title"]].to_string())