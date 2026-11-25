"""Label call transcripts:  python run.py INPUT.jsonl OUTPUT.jsonl

INPUT: one JSON object per line with transcript_id, call_started_at, timezone, transcript.
OUTPUT: one JSON object per line with transcript_id, disposition, sub_disposition, lead_quality, next_call_at.
Needs the GROQ_API_KEY environment variable."""
import json, sys, time
from datetime import datetime, timedelta
from labeler import MODEL, extract, to_labels
from timeparse import at_11, fmt, IST


def fallback(call_started_at):
    """If the API fails for a record, still write the most common label set so the record is valid."""
    start = datetime.fromisoformat(call_started_at).astimezone(IST)
    return {"disposition": "Follow-up Required", "sub_disposition": "Further Discussion",
            "lead_quality": "Medium", "next_call_at": fmt(at_11(start.date() + timedelta(days=1)))}


def main(input_path, output_path):
    rows = [json.loads(line) for line in open(input_path, encoding="utf-8") if line.strip()]
    print("model:", MODEL)
    started, tokens_in, tokens_out, failed = time.time(), 0, 0, []

    with open(output_path, "w", encoding="utf-8") as f:
        for row in rows:
            tid = row["transcript_id"]
            try:
                out, usage = extract(row)
                labels = to_labels(out, row["call_started_at"])
                tokens_in += usage.prompt_tokens
                tokens_out += usage.completion_tokens
                print(f"{tid}: done")
            except Exception as e:
                labels = fallback(row["call_started_at"])
                failed.append(tid)
                print(f"{tid}: FAILED, fallback used ({str(e)[:100]})")
            f.write(json.dumps({"transcript_id": tid, **labels}, ensure_ascii=False) + "\n")

    print(f"\nwrote {len(rows)} records to {output_path} | failed: {len(failed)} {failed if failed else ''}")
    print(f"tokens: {tokens_in} in / {tokens_out} out | time: {round(time.time() - started)}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])