import pandas as pd

SEED = 42
PER_TAHUN = 35

df = pd.read_csv("data/raw/cnbc_shortlist.csv")
df["tahun"] = pd.to_datetime(df["date"], errors="coerce").dt.year
df = df.dropna(subset=["tahun"])

sampel = (
    df.groupby("tahun")
      .sample(n=PER_TAHUN, random_state=SEED)
      .sort_values("date")
      .reset_index(drop=True)
)

sampel.drop(columns=["tahun"]).to_csv(
    "data/raw/cnbc_shortlist_sampel.csv", index=False
)

print("Total sampel:", len(sampel))
print()
print(sampel["tahun"].value_counts().sort_index().to_string())