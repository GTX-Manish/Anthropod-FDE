"""Label call transcripts:  python run.py INPUT.jsonl OUTPUT.jsonl

INPUT: one JSON object per line with transcript_id, call_started_at, timezone, transcript.
OUTPUT: one JSON object per line with transcript_id, disposition, sub_disposition, lead_quality, next_call_at.
Needs the GROQ_API_KEY environment variable.

If a model call still fails after the SDK's retries (bad key, rate or daily limit, network), the run stops.
Records finished before the failure are kept, nothing is guessed for the rest, and the exit code is 1."""
import json, sys, time
from labeler import MODEL, extract, to_labels


def main(input_path, output_path):
    rows = [json.loads(line) for line in open(input_path, encoding="utf-8") if line.strip()]
    print("model:", MODEL)
    started, tokens_in, tokens_out, written = time.time(), 0, 0, 0

    with open(output_path, "w", encoding="utf-8") as f:
        for row in rows:
            tid = row["transcript_id"]
            try:
                out, usage = extract(row)
            except Exception as e:
                print(f"\nSTOPPED at {tid}: the model call failed after retrying ({str(e)[:200]})")
                print(f"{written} of {len(rows)} records were written to {output_path}. No labels were guessed for the rest.")
                print("Fix the cause (API key, rate or daily limit, network) and run the same command again.")
                sys.exit(1)
            labels = to_labels(out, row["call_started_at"])
            f.write(json.dumps({"transcript_id": tid, **labels}, ensure_ascii=False) + "\n")
            f.flush()
            written += 1
            tokens_in += usage.prompt_tokens
            tokens_out += usage.completion_tokens
            print(f"{tid}: done")

    print(f"\nwrote {written} of {len(rows)} records to {output_path}")
    print(f"tokens: {tokens_in} in / {tokens_out} out | time: {round(time.time() - started)}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])