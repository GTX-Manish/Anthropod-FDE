# Task 2: customer gender from call transcripts

## Run it

```bash
python gender.py data/input.jsonl outputs/gender_predictions.jsonl
```

Each output line is `{"transcript_id", "gender", "female_score", "male_score"}`. The gender is `male`, `female` or `unknown`. It uses the Python standard library only: no transformer, no model and no API.

## First thought

The first thought that came to my mind after reading "Build logic to identify the customer's gender from the assignment transcripts" was to simply give it to an LLM, and my job would be done. But then I read the line "without using a transformer-based model."

## Approach

Since I was working on the first part, where I had to label the transcripts, I had already read almost half of them.

So I knew that the words "sir" or "ma'am" were used in almost every call, and this could play a vital role in determining the gender of the speaker on the call. (I had a doubt: should "customer" mean the person speaking on the call, or the patient? I asked, and it was confirmed that it means the caller.)

Other than that, when the speaker was talking for someone else, words like "my wife" or "my husband" could be used to determine the gender of the speaker.

I decided to use a point system:

| Clue | Whose words | Points | Why |
|---|---|---|---|
| "my husband" → female, "my wife" → male | caller | 3 each | The caller describes themselves; the strongest clue |
| "Mrs/Ms/Miss Name" → female, "Mr Name" → male | agent | 2 each | Strong but rare |
| "ma'am / madam" → female, "sir" → male | agent | 1 each | Agents repeat it many times, so it adds up |

### Why points instead of a simple rule

A simple rule like "if the agent says ma'am, it's female" breaks on real calls. In AVT-002 the agent says "sir" 16 times and "ma'am" once, a slip or a word meant for someone else in the room. Counting every clue across the whole call lets the 16 outvote the one slip.

The weights are set so that one strong clue can decide a call on its own, but one weak clue cannot:
- One "my wife" (3 points) or one "Mr. Arjun" (2 points) is enough by itself, because the caller is describing themselves, or the agent is using their name.
- One "sir" (1 point) is not enough. A single "sir" in a whole call is too easily a slip, so that call stays `unknown` (as in AVT-019 and AVT-042).

At the end:
- If there are fewer than 2 points in total, or the female and male scores are too close (the gap is less than half the total), the answer is `unknown`. I would rather say "unknown" than guess.
- Otherwise, the side with more points wins.

## The plan was to simply use regex to deal with this.

1. split_turns(transcript) - Collecting everything the agent said into one string and everything the customer said into another, and returns both.

Why: the caller also says "sir" or "ma'am", but that's addressed to the agent, so it tells you about the agent. Only the agent's sir/ma'am describes the caller.

2. Male/Female scores: Each clue adds points to one side. Stronger clues count more.

3. total = female + male scores. 

So, if `total < 2 or abs(female - male)/total < 0.5` then this means that there is too less information or ambigious information. This will result in "unknown". Else, if female > male then "female" otherwise "male"

### A mistake I fixed

My first version counted the title "Ms" without caring about capital letters. When I checked which words were adding female points, I found that agents often describe the doctors as "MD, MS doctors". Here "MS" is a medical degree (Master of Surgery), not the title "Ms". That was adding false female points in AVT-005, AVT-014, AVT-018 and AVT-046.

None of those predictions flipped, because the agent said "sir" many more times. But in a call with only one or two "sir"s, it could have turned a male caller into female or unknown. So now a title only counts when it is written with a capital letter and followed by a name, like "Miss Kavita" or "Mr. Kartik".

## Results

On the 50 calls: **31 male, 14 female, 5 unknown.**

- **AVT-008** is unknown because two people speak on the customer side. The husband says "I am Renu's husband speaking", and later the wife says "let me talk to my husband".
- **AVT-015, AVT-019, AVT-039 and AVT-042** are unknown because the agent barely addresses the caller.

## How I checked it

There are no gold gender labels, so I checked it in three ways:

1. **Clues agree with each other.** In all 9 calls where the caller says "my husband" or "my wife", the agent's "sir/ma'am" points the same way.
2. **I read the weakest predictions** (scores of 2–4) myself, and they were all correct.
3. **Edge cases.** `edge_cases.csv` has 30 short test calls with tricky situations: a caller saying "ma'am" to a female agent, a son calling for his mother, "MD, MS doctors", an agent saying "sir" and being corrected to "ma'am", a call with only "Mr. Arjun", and a call with no clues at all. All 30 came out right (`python check_gender.py data/edge_cases.csv outputs/edge_gender.jsonl`). These cases were written for this test, so they show the rules work as intended, not that they will be perfect on every new call.

## Drawbacks

- There are only a few ways to determine the gender: "sir/ma'am", "my wife/husband" and titles like "Mr". If someone says "my grandson" or "my granddaughter" and the agent never says "sir/ma'am", the algorithm can't determine the gender and returns `unknown`.
- It depends on this call centre's habit of calling people "sir" or "ma'am", and on the agent using the right one.
- "My husband / my wife" assumes an opposite-sex marriage.
- If two people talk on the customer side of the same call, it usually returns `unknown`.
- A possible improvement is self-introductions like "I am her son" or "I'm his mother". This appears only once in the 50 calls (AVT-008) and wouldn't change any result, so I didn't add it.

## Why not another model?

Since the restriction was only on transformer-based models, I did think about using some other model instead, like a name-to-gender model, a classical classifier, or a pre-trained non-transformer model from GitHub. But I didn't feel any need to, because the transcripts already had the answer in plain words: the agent says "sir" or "ma'am" again and again in almost every call. Simple rules on those words were enough, and with them every prediction can be explained.