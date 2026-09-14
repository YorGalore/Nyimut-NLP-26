import pandas as pd

df = pd.read_csv("data/raw/cnbc_index.csv")
df["tahun"] = pd.to_datetime(df["date"], errors="coerce").dt.year

judul = df["title"].fillna("").str.lower()
slug = df["url"].fillna("").str.lower()

pola = "live updates|live blog|war updates|live-updates|live-blog"
live = judul.str.contains(pola, regex=True) | slug.str.contains(pola, regex=True)

# Semua artikel soal Ukraina, terlepas dari format live blog
ukraina = judul.str.contains("ukraine|russia|putin|kyiv|zelenskyy", regex=True)

ringkas = pd.DataFrame({
    "total": df["tahun"].value_counts(),
    "ukraina": df.loc[ukraina, "tahun"].value_counts(),
    "live_ukraina": df.loc[live & ukraina, "tahun"].value_counts(),
}).sort_index().fillna(0).astype(int)

print("Artikel Ukraina vs live blog Ukraina per tahun:")
print(ringkas.to_string())
print()

print("Contoh judul Ukraina di 2022 (10 teratas):")
m22 = ukraina & (df["tahun"] == 2022)
print(df.loc[m22, "title"].head(10).to_string())
print()

print("Contoh judul live blog di 2024 (5 teratas):")
m24 = live & (df["tahun"] == 2024)
print(df.loc[m24, "title"].head(5).to_string())