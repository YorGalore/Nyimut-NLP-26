import pandas as pd
import config as C

df = pd.read_csv(C.CNBC_RAW_CSV)

print("dtype kolom section:", df["section"].dtype)
print("jumlah kosong (NaN):", df["section"].isna().sum())
print()

# cari baris yang nilainya bukan string
aneh = df["section"].apply(lambda x: not isinstance(x, str))
print("Baris dengan tipe bukan string:", aneh.sum())
print()
print("Contoh nilai anehnya:")
print(df.loc[aneh, "section"].head(10).tolist())