"""python make_input.py calls.csv input.jsonl - keep only the four input fields (gold labels removed)."""
import csv, json, sys

KEEP = ["transcript_id", "call_started_at", "timezone", "transcript"]
with open(sys.argv[2], "w", encoding="utf-8") as f:
    for r in csv.DictReader(open(sys.argv[1], encoding="utf-8", newline="")):
        f.write(json.dumps({k: r[k] for k in KEEP}, ensure_ascii=False) + "\n")