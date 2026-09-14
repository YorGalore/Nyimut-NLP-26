from pathlib import Path
import pandas as pd
import config as C

ROOT = Path(__file__).resolve().parent.parent
df = pd.read_csv(ROOT / "data/raw/cnbc_sampel_hasil.csv")

df["n_tok"] = df["description"].fillna("").str.split().str.len()
df["live"] = df["body"].fillna("").str.len() == 0

print("MIN_TOKENS di config:", C.MIN_TOKENS)
print()
print("Panjang deskripsi (token):")
print(df.groupby("live")["n_tok"].describe()[["count", "min", "mean", "max"]].to_string())
print()
print("Live blog yang akan terbuang filter panjang:",
      ((df["live"]) & (df["n_tok"] < C.MIN_TOKENS)).sum(), "dari", df["live"].sum())