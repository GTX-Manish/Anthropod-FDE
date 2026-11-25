"""python test_parse.py - checks next_call_at against the Label Rules examples and real calls (no API)."""
from labeler import next_call_at

def out(disposition, callback=None, defers="no"):
    return {"disposition": disposition, "callback_agreed": "yes" if callback else "no",
            "callback_time_text": callback, "customer_defers": defers}

CASES = [
    ("2026-11-09T14:00:00+05:30", out("Follow-up Required", "tomorrow at 4"), "2026-11-10T16:00:00+05:30"),   # EX1
    ("2026-11-09T14:00:00+05:30", out("Follow-up Required", defers="yes"), "2026-11-12T11:00:00+05:30"),      # EX2
    ("2026-11-09T14:00:00+05:30", out("Appointment Scheduled"), None),                                        # EX3
    ("2026-11-09T14:00:00+05:30", out("Follow-up Required"), "2026-11-10T11:00:00+05:30"),                    # EX4
    ("2026-11-09T14:00:00+05:30", out("Not Interested", "tomorrow"), None),                                   # EX5
    ("2026-10-14T13:19:21+05:30", out("Follow-up Required", "tomorrow evening"), "2026-10-15T18:00:00+05:30"),  # AVT-004
    ("2026-10-15T10:39:36+05:30", out("Follow-up Required", "this evening"), "2026-10-15T18:00:00+05:30"),      # AVT-044
    ("2026-10-15T14:11:01+05:30", out("Follow-up Required", "in 15 minutes"), "2026-10-15T14:26:01+05:30"),     # AVT-047
    ("2026-10-15T14:11:01+05:30", out("Follow-up Required", "15 minutes"), "2026-10-15T14:26:01+05:30"),        # AVT-047
    ("2026-10-15T18:28:03+05:30", out("Follow-up Required", "on the 26th"), "2026-10-26T11:00:00+05:30"),       # AVT-017
    ("2026-10-14T10:38:33+05:30", out("Follow-up Required", "on the 22nd"), "2026-10-22T11:00:00+05:30"),       # AVT-023
    ("2026-10-17T12:36:14+05:30", out("Follow-up Required", "next week"), "2026-10-19T11:00:00+05:30"),         # AVT-040
]

fails = 0
for start, o, want in CASES:
    got = next_call_at(o, start)
    fails += got != want
    print("OK  " if got == want else "FAIL", o["callback_time_text"], "->", got, "| expected", want)
print(f"\n{len(CASES) - fails}/{len(CASES)} passed")
raise SystemExit(1 if fails else 0)