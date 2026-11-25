"""python evaluate.py GOLD.csv PREDICTIONS.jsonl
Per-field accuracy, whole-record exact match and the estimated 70-point label score."""
import csv, json, sys

FIELDS = ["disposition", "sub_disposition", "lead_quality", "next_call_at"]
WEIGHTS = {"disposition": 15, "sub_disposition": 20, "lead_quality": 15, "next_call_at": 20}

gold = {r["transcript_id"]: {f: (None if r[f] == "null" else r[f]) for f in FIELDS}
        for r in csv.DictReader(open(sys.argv[1], encoding="utf-8", newline=""))}
pred = {p["transcript_id"]: p for p in map(json.loads, (l for l in open(sys.argv[2], encoding="utf-8") if l.strip()))}

hit, exact = {f: 0 for f in FIELDS}, 0
for tid, g in gold.items():
    p = pred.get(tid, {})
    ok = {f: p.get(f) == g[f] for f in FIELDS}
    ok["sub_disposition"] &= ok["disposition"]          # sub only counts with the right parent
    exact += all(ok.values())
    for f in FIELDS:
        hit[f] += ok[f]
    bad = [f"{f}: {p.get(f)} (gold {g[f]})" for f in FIELDS if not ok[f]]
    if bad:
        print(tid, " | ".join(bad))

n = len(gold)
print(f"\nrecords: {n}")
for f in FIELDS:
    print(f"{f}: {hit[f]}/{n} = {hit[f] / n:.0%}")
print(f"whole-record exact match: {exact}/{n}")
print(f"estimated label score: {sum(WEIGHTS[f] * hit[f] / n for f in FIELDS):.1f}/70")