import pandas as pd

PATH = "data/raw/cnbc_raw.csv"

df = pd.read_csv(PATH)
df["body_len"] = df["body"].fillna("").str.len()

kosong = df["body_len"] == 0

print("Total artikel :", len(df))
print("Body kosong   :", kosong.sum())
print("Success rate  : {:.0%}".format(1 - kosong.mean()))
print()
print("--- Yang gagal ---")
print(df.loc[kosong, ["section", "title"]].to_string())