import pandas as pd

df = pd.read_csv("data/raw/cnbc_sampel_hasil.csv")
sec = df["section"].fillna("").str.lower()
df["paywall"] = sec.str.contains("pro:|investing club", regex=True)

print("Paywall di sampel:", df["paywall"].sum())
print()
print("--- URL artikel berbayar ---")
for u in df.loc[df["paywall"], "url"]:
    print(" ", u.replace("https://www.cnbc.com", ""))
print()
print("--- URL artikel normal (5 pembanding) ---")
for u in df.loc[~df["paywall"], "url"].head(5):
    print(" ", u.replace("https://www.cnbc.com", ""))