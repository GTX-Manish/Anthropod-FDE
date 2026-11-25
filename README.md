# Anthropod FDE assignment: Aster Vale Pain Clinic

This repo has the two tasks in separate folders:

| Folder | Task |
|---|---|
| [task1/](task1/README.md) | Label each call with `disposition`, `sub_disposition`, `lead_quality` and `next_call_at`, using an open model on Groq plus Python rules |
| [task2/](task2/README.md) | Find the caller's gender without a transformer model, using rules only |
| `data/` | The 50 labelled calls, my 30 edge-case test calls, and the input files made from them (used by both tasks) |

## Setup

Run every command from this main folder.

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
export GROQ_API_KEY=your_key                        # only Task 1 needs it. Windows PowerShell: $env:GROQ_API_KEY="your_key"
```

## Main commands

```bash
python -u task1/run.py INPUT.jsonl predictions.jsonl               # Task 1
python task2/gender.py INPUT.jsonl gender_predictions.jsonl        # Task 2
```

`INPUT.jsonl` has one JSON object per line with `transcript_id`, `call_started_at`, `timezone` and `transcript`. Each folder's README explains the approach, the results and how to reproduce them.
