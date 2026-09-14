from pathlib import Path
import json

CKPT = Path(r"C:\Users\anabe\NLP-Nyimut\Nyimut-NLP-26\data\raw\checkpoints\articles")

total = rusak = 0
for f in sorted(CKPT.glob("*.jsonl")):
    bad = []
    for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            continue
        total += 1
        try:
            json.loads(line)
        except json.JSONDecodeError:
            bad.append(i)
            rusak += 1
    if bad:
        print(f"{f.name}  ->  baris rusak: {bad}")

print()
print("Total baris :", total)
print("Rusak       :", rusak)