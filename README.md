# Aster Vale Pain Clinic: call transcript labelling

This repo has both parts of the assignment:

1. **Task 1:** label each call with `disposition`, `sub_disposition`, `lead_quality` and `next_call_at`.
2. **Task 2:** find the caller's gender without a transformer model. See [GENDER.md](GENDER.md).

## Run it

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
export GROQ_API_KEY=your_key                        # Windows PowerShell: $env:GROQ_API_KEY="your_key"

python -u run.py INPUT.jsonl predictions.jsonl
```

- **Input:** one JSON object per line with `transcript_id`, `call_started_at`, `timezone` and `transcript`.
- **Output:** one JSON object per line with exactly `transcript_id`, `disposition`, `sub_disposition`, `lead_quality` and `next_call_at`. `next_call_at` is an ISO timestamp with seconds and `+05:30`, or JSON `null`.

To reproduce my numbers on the 50 labelled calls:

```bash
python make_input.py data/calls.csv data/input.jsonl     # removes the gold columns
python -u run.py data/input.jsonl outputs/predictions.jsonl
python evaluate.py data/calls.csv outputs/predictions.jsonl
python test_parse.py                                 # date rule tests, no API calls
```

**One thing to check:** the end of the run should say `failed: 0`. If Groq can't answer a call even after retrying (for example, the daily token limit is used up), that call still gets a valid fallback label so the output file is complete, and the run tells you which calls failed. On Groq's free tier, 50 calls take about 20 minutes because of the rate limits.

## First thought

My first idea was to give the whole transcript to the model and ask for all four labels at once. But after reading the Label Rules, I realised most of the difficulty is not reading the call. It's the rules: the order of precedence between dispositions, which sub-disposition belongs to which disposition, the 7-day line for High lead quality, and especially the callback-time rules (tomorrow = +1, no time = 11:00, vague = +3 days, and so on). An LLM is good at reading a messy call, but not reliable at date maths and strict rule-following.

## Approach

So I split the work:

- **The model reads the call.** It fills a short checklist of facts first, and only then the labels:
  - the customer's last statement
  - whether a rejection had a condition
  - the main blocker
  - whether a booking was confirmed
  - whether there is a real pain need
  - whether the customer put things off
  - whether a callback was agreed, and the exact words for its time.
- **Python applies the rules.** It keeps the labels consistent with the model's own checklist. For example, a conditional rejection can't be Not Interested, and a named blocker owns the sub-disposition. Python also turns the callback words ("tomorrow evening", "on the 26th", "in 15 minutes") into the exact timestamp, using the call's start time.

I started with two model calls per transcript (one for the outcome, one for the scheduling), and prototyped on the smaller `gpt-oss-20b` model. But Groq's free tier allows 200,000 tokens a day, and two calls per transcript didn't fit a full run. So I moved to one call with the checklist, which halved the tokens and kept the accuracy.

The full prompt is in `labeler.py` (`SYSTEM_PROMPT`). The user message is just `Call date: YYYY-MM-DD (Weekday)` followed by the transcript. No example transcripts are put in the prompt, and only the four input fields are sent to the model.

## Model and settings

| Setting | Value |
|---|---|
| Model | Groq, `openai/gpt-oss-120b` (fixed in code) |
| Temperature | 0 |
| Reasoning effort | `low` |
| Max completion tokens | 4096 |
| Output | Groq structured outputs, `json_schema` with `strict: true` |
| Timeout | 60 s per request |
| Retries | Groq SDK, `max_retries=8` (rate limits, network and server errors) |
| JSON handling | Strict schema, then `json.loads`, then the consistency checks and the valid-pair check. If anything fails, the call gets a fallback record (Follow-up Required / Further Discussion / Medium / next day 11:00) |
| Python | 3.9+ (I used 3.14). `tzdata` is needed on Windows. |
| Dependencies | `requirements.txt` |

## Files

| File | What it does |
|---|---|
| `run.py` | The one command: reads the input JSONL and writes the predictions JSONL |
| `labeler.py` | Prompt, schema, Groq call, consistency checks, `next_call_at` logic |
| `timeparse.py` | Turns callback words into an exact IST time |
| `evaluate.py` | Per-field accuracy, exact match and the estimated 70-point score (it can also score a small subset of calls) |
| `make_input.py` | Turns the labelled CSV into input JSONL, without the gold columns |
| `test_parse.py` | 12 date tests: the sheet's EX1–EX5 examples plus phrases from real calls |
| `predictions.jsonl` | My final predictions for the 50 calls |
| `edge_cases.csv` | 30 test calls I wrote for situations the 50 calls don't have |
| `gender.py`, `check_gender.py`, `gender_predictions.jsonl` | Task 2 |
| `run_log.txt`, `eval_log.txt` | Output of the final run and its evaluation |

## Results

Final run on the 50 labelled calls:

| Field | Correct | Points (brief's weights) |
|---|---|---|
| disposition | 49/50 | 14.7 / 15 |
| sub_disposition | 36/50 | 14.4 / 20 |
| lead_quality | 46/50 | 13.8 / 15 |
| next_call_at | 43/50 | 17.2 / 20 |
| **Total** | | **60.1 / 70** |
| Whole-record exact match | 32/50 | |

**Cost:** 176,208 input and 18,219 output tokens for the 50 calls, about 3,900 tokens per call. At Groq's listed price for this model at the time ($0.15 / $0.60 per million input/output tokens), that's about **$0.04** for the whole run. It took 1,201 seconds on the free tier, mostly waiting on rate limits. Each model call itself took about 1.4 seconds.

## Error analysis

### How the score moved

| Stage | Score |
|---|---|
| First single-call run on calls 1–20 | 55.5 / 70 |
| Calls 21–40, before I tuned anything on them | 59.5 / 70 |
| Final clean run with the final code | 60.1 / 70 (calls 41–50: 52) |

### Changes I made because of what the tests showed

I didn't write these rules up front. Each one came from a call that went wrong when I compared my output with the gold labels.

| What I saw | Call(s) | What I changed |
|---|---|---|
| "Only when you tell me will I want it… Forget it" was read as a final refusal | AVT-042 | Added `rejection_condition`, and a Python check stops a conditional rejection from becoming Not Interested |
| That condition field then fired on plain anger ("What kind of rule is this… I don't want it") and cancelled a real refusal | AVT-010 | A condition needs explicit words (if / unless / only when / until). Anger or complaints don't count |
| The customer said it "isn't exactly pain, it's stiffness", but lead quality came out Medium | AVT-042 | `pain_need: unclear` forces Not Assessable |
| Blockers came back as "none" when they were implied ("I'll consult my mother", "my mom is away", asking for a concession) | AVT-004, 019, 028 | Blockers can be implied. If there's no booking, the model must pick the best-fitting one |
| Information Requested was used for "I'll find out more" and for routine location details | AVT-018, 025, 032 | Information Requested only when the customer will review specific information the clinic sends |
| A callback replaced the real blocker (Specific Callback instead of Family Discussion) | AVT-004 | A named blocker owns the sub-disposition even when a callback is agreed |
| "I will let you know because my husband is away" wasn't treated as putting things off, so +1 day instead of +3 | AVT-001 | Added waiting on a person or an event to the deferral examples |
| Some calls came back empty (HTTP 400) | AVT-001 | Set `max_completion_tokens=4096` and `reasoning_effort="low"` |
| "15 minutes" and "on the 26th" weren't understood by the date code | AVT-047, 017 | The parser now handles a bare "N minutes/hours" and explicit dates |
| One callback field mixed "a callback was agreed" with "the customer put it off", giving +1 where gold had +3 | AVT-001, 006, 013, 018, 019 | Split it into `customer_defers` and `callback_agreed` |
| My family definition pulled travel cases into Family | AVT-001, 019 | A relative being away or unable to accompany the patient is travel. Family is only discussion, approval or decision |
| Ongoing treatment elsewhere was labelled Treatment Concern, and insisting on a senior doctor was labelled Information Requested | AVT-006, 014, 018 | Current treatment comes first. Doubts about the doctor or "researching the treatment" are treatment concerns |
| Callbacks the agent proposed while sending details ("I'll contact you on the 22nd") were missed, and "next week after Dussehra" was read as next Monday | AVT-023, 040, 024 | Agent-proposed calls with a "yes" count. A day tied to an unresolved event is vague |
| The model copied the customer's reply ("in between") instead of the agent's time ("next week") | AVT-040 | The callback time is taken from the proposal, not the reply |
| A plain "I'll call you" hid the real reason (doubts about results, work timing) | AVT-022, 031 | An unresolved reason beats a plain postponement |
| Low was given to interested customers with a cost blocker. My first fix then went too far the other way | AVT-028, 035, then 006, 022 | Low only for no current intent, or putting it off for more than 30 days |

### Where it still goes wrong

1. **Choosing between two blockers.** Most of the 14 sub-disposition misses are family vs travel (AVT-001, 034, 040, 048) or current treatment vs the others (AVT-030, 038). Some of these are close calls even when I read them myself.
2. **"The customer put it off" fires too often.** A plain "Okay, thank you, bye" gets read as a deferral, so the callback goes to +3 days where gold has +1 (AVT-015, 041, 042, 048, 050). This is the biggest reason for callback errors on calls 41–50.
3. **A missed short callback and a borderline booking.** "Call you back in 15 minutes" was missed (AVT-047). AVT-037 ("Don't confirm it… keep the appointment for 2 o'clock") is a booking in gold, but not for the model.
4. **Low vs Medium lead quality** changes from run to run (AVT-006, 022, 040).

### The model isn't perfectly repeatable

The full run and the final run used the same prompt, model and temperature 0, but scored 61.5 and 60.1. A few calls changed answers between the two runs (e.g. AVT-006, 013, 030, 044, 050). So a difference of about ±1.5 points on 50 calls is just noise, and I couldn't judge very small prompt changes on this data.

### Edge-case test

The 50 calls have no Invalid Lead, Unable to Assess, Do Not Contact, Online Consultation or Rescheduled examples, but the private set might. So I wrote 30 short test calls for these and for the tricky callback-time rules (`edge_cases.csv`). The expected labels are my own reading of the Label Rules.

- **Result:** about 60/70 equivalent, with 18/30 exact matches.
- **What it got right:** wrong number, no pain need, test call, a 12-year-old patient, a silent call, online and rescheduled bookings, and every callback-date phrase ("parso in the evening", "in two hours", "at 5" after 5 pm, "next Friday", "December 3rd", and a cancelled callback becoming a vague deferral).
- **What it got wrong:**
  - "Remove my number, don't call again" came out as Explicit Refusal instead of Do Not Contact.
  - Someone living abroad permanently who refuses online care came out as Not Interested instead of Invalid Lead.
  - A booking 11 days away came out High instead of Medium, because Python never sees the appointment date.
  - Low vs Medium was inconsistent.

### One fix I added after testing

The edge-case test showed that "Remove my number, don't call me again" came out as Explicit Refusal. So I added a small Python check: if the customer's last few lines say "don't call me again", "stop calling" or "remove my number", the call becomes Not Interested / Do Not Contact. A plain "don't call tomorrow" doesn't trigger it. This check doesn't fire on any of the 50 calls, so all the results above stay the same.

## Constraints I worked with

- The brief asked for an open model through Groq, so I used `openai/gpt-oss-120b` on Groq's free tier. The free tier has two limits for this model: 8,000 tokens per minute and 200,000 tokens per day.
- One full run of the 50 calls uses about 194,000 tokens (176,208 in and 18,219 out), so I could do only about one full run per day. Because of this, I tested most prompt changes on small groups of calls first and did full runs only when a change looked good.
- I set the reasoning effort to `low`. At the default effort, the model used 700 to 1,500 output tokens per call, which would push a full run past the daily limit. Some calls also came back empty because the model used its whole output budget on thinking. At `low`, each call uses about 300 to 400 output tokens and those empty responses stopped.
- The per-minute limit means a full run takes about 20 minutes, most of it spent waiting for the rate limit.

## If I had more time

- **Enforce the 7-day rule in Python.** Ask the model for the exact words of the confirmed appointment time (like it already does for callbacks), and let Python count the days, so a booking 7 or more days away is always Medium.
- **A separate "outside service area" field,** so a caller who lives abroad and refuses online care becomes Invalid Lead instead of Not Interested.
- **Fix the deferral over-use properly.** I tried making the model quote the customer's own words before counting a deferral. It fixed some calls (AVT-015) but broke others where the agent proposed the vague postponement and the customer agreed (AVT-024, "I'll call you after Dussehra", "Okay"). The rules count both, so the next version should accept a postponement from either side when the other side agrees. I kept this out of the submission because it wasn't proven better yet.
- **Run each version a few times and compare averages.** Two identical runs differed by about 1.5 points, so single runs on 50 calls can't show small improvements. For fields that flip between runs (like Low vs Medium), I'd also try asking the model 3 times and taking the majority answer.
- **Try a higher reasoning effort** on the calls where the model is unsure, and check whether the accuracy gain is worth the extra tokens and time.

## If I had more data

- **A proper held-out set.** With a few hundred labelled calls, I could tune on one part and measure on a part I never looked at, instead of the 10 calls I kept aside.
- **Targeted examples for the hard boundaries.** Most errors are family vs travel and current treatment vs treatment concern. A handful of real labelled examples of each, added to the prompt, would likely help more than more rule wording.
- **A confusion table per field,** to see exactly which labels get mixed up with which, instead of reading the misses one by one.
- **Confirming the borderline gold labels with the team.** A few calls (like AVT-037, "Don't confirm it… keep the appointment for 2 o'clock") could be read either way. Knowing how the team decides those would let me write the rule once instead of guessing.