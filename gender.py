"""Guess the caller's (customer's) gender from a call transcript with simple rules, no ML model.

Clues, strongest first:
  1. The caller mentions "my husband" (female) or "my wife" (male).
  2. How the agent addresses the caller: "ma'am"/"madam" (female) or "sir" (male).
  3. A title the agent puts before a name: "Mrs/Ms/Miss Kavita" (female) or "Mr. Kartik" (male).
Only the agent's words are used for sir/ma'am, because callers also say "sir" or "ma'am" to the agent.

Usage: python gender.py INPUT.jsonl OUTPUT.jsonl
"""
import json, re, sys

MAAM = r"\b(?:ma'?am|madam|mam)\b"
SIR = r"\bsir\b"


def count(pattern, text, case_sensitive=False):
    return len(re.findall(pattern, text, 0 if case_sensitive else re.IGNORECASE))


def split_turns(transcript):
    sides = {"Agent": [], "Customer": []}
    for line in transcript.splitlines():
        m = re.match(r"\s*(Agent|Customer)\s*:\s*(.*)", line)
        if m:
            sides[m.group(1)].append(m.group(2))
    return " ".join(sides["Agent"]), " ".join(sides["Customer"])


def predict(transcript):
    agent, customer = split_turns(transcript)

    # titles must be capitalised and followed by a name, so the degree "MS" is not read as "Ms"
    female = (3 * count(r"\bmy husband\b", customer) + count(MAAM, agent)
              + 2 * count(r"\b(?:Mrs|Ms|Miss)\.?\s+[A-Z][a-z]", agent, case_sensitive=True))
    male = (3 * count(r"\bmy wife\b", customer) + count(SIR, agent)
            + 2 * count(r"\bMr\.?\s+[A-Z][a-z]", agent, case_sensitive=True))

    total = female + male
    if total < 2 or abs(female - male) / total < 0.5:   # too little or too mixed evidence
        gender = "unknown"
    else:
        gender = "female" if female > male else "male"
    return {"gender": gender, "female_score": female, "male_score": male}


if __name__ == "__main__":
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        for line in open(sys.argv[1], encoding="utf-8"):
            if line.strip():
                row = json.loads(line)
                result = {"transcript_id": row["transcript_id"], **predict(row["transcript"])}
                f.write(json.dumps(result) + "\n")
                print(result)