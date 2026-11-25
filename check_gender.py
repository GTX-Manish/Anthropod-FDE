"""python check_gender.py GOLD.csv GENDER_PREDICTIONS.jsonl - gender accuracy against a 'gender' column."""
import csv, json, sys

gold = {r["transcript_id"]: r["gender"] for r in csv.DictReader(open(sys.argv[1], encoding="utf-8", newline=""))}
pred = {p["transcript_id"]: p["gender"] for p in map(json.loads, (l for l in open(sys.argv[2], encoding="utf-8") if l.strip()))}

right = 0
for tid, g in gold.items():
    if pred.get(tid) == g:
        right += 1
    else:
        print(f"{tid}: predicted {pred.get(tid)}, expected {g}")
print(f"\ngender correct: {right}/{len(gold)}")