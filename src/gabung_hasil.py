from pathlib import Path
import json
import pandas as pd

ROOT = Path(r"C:\Users\anabe\NLP-Nyimut\Nyimut-NLP-26")
CKPT = ROOT / "data/raw/checkpoints/articles"
OUT = ROOT / "data/raw/cnbc_raw.csv"

rows, dilewati = [], 0
for f in sorted(CKPT.glob("*.jsonl")):
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            dilewati += 1

out = pd.DataFrame(rows).drop_duplicates(subset=["url"])

sec = out.get("section", pd.Series("", index=out.index)).fillna("").str.lower()
berbayar = sec.str.contains("pro:|investing club", regex=True)
n_berbayar = int(berbayar.sum())
out = out[~berbayar].copy()

out["article_id"] = out["url"]
out["type"] = "article"
out["search_keyword"] = out.get("matched_terms", "")
out["keyword_group"] = "html_sitemap"
if "section" not in out:
    out["section"] = ""

out["description"] = (
    out.get("description", "").fillna("")
    + " "
    + out.get("body", "").fillna("").str.slice(0, 2000)
).str.strip()

out.to_csv(OUT, index=False)

print("Baris rusak dilewati :", dilewati)
print("Dibuang (berbayar)   :", n_berbayar)
print("Artikel terkumpul    :", len(out))
print("Punya isi artikel    :", out["body"].notna().sum())
print("Tersimpan            :", OUT)