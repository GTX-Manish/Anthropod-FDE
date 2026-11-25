"""One Groq call per transcript: the model fills an evidence checklist and the four labels.
Python then enforces consistency guards and computes next_call_at from the callback words."""
import json
import re
from datetime import datetime, timedelta
from groq import Groq
from timeparse import parse_time_text, at_11, fmt, IST

MODEL = "openai/gpt-oss-120b"
SETTINGS = {"temperature": 0, "max_completion_tokens": 4096, "reasoning_effort": "low"}

VALID = {
    "Appointment Scheduled": {"Clinic Visit", "Online Consultation", "Rescheduled"},
    "Follow-up Required": {"Specific Callback", "Vague Deferral", "Family Discussion", "Cost Concern",
                           "Travel Constraint", "Current Treatment", "Treatment Concern",
                           "Information Requested", "Further Discussion"},
    "Not Interested": {"Explicit Refusal", "Do Not Contact"},
    "Invalid Lead": {"Wrong Contact", "No Pain Need", "Outside Service Area", "Policy Exclusion", "Test Enquiry"},
    "Unable to Assess": {"Incomplete Conversation"},
}
DEFAULT_SUB = {"Appointment Scheduled": "Clinic Visit", "Follow-up Required": "Further Discussion",
               "Not Interested": "Explicit Refusal", "Invalid Lead": "No Pain Need",
               "Unable to Assess": "Incomplete Conversation"}
BLOCKER_SUB = {"family": "Family Discussion", "cost": "Cost Concern", "travel": "Travel Constraint",
               "current_treatment": "Current Treatment", "treatment_concern": "Treatment Concern"}
NO_CALLBACK = {"Invalid Lead", "Not Interested", "Unable to Assess"}

# a customer asking the clinic to stop contacting them (not "don't call tomorrow")
NO_CONTACT = (r"\b(?:don'?t|do not|never)\s+call\s+(?:me\s+)?(?:again|anymore|any more)\b"
              r"|\bstop calling\b|\b(?:remove|delete)\s+my\s+(?:number|name|details)\b")

STR_OR_NULL = {"type": ["string", "null"]}
YES_NO = {"type": "string", "enum": ["yes", "no"]}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["last_customer_statement", "rejection_condition", "main_blocker", "booking_confirmed",
                 "pain_need", "customer_defers", "callback_agreed", "callback_time_text",
                 "disposition", "sub_disposition", "lead_quality"],
    "properties": {
        "last_customer_statement": STR_OR_NULL,
        "rejection_condition": STR_OR_NULL,
        "main_blocker": {"type": "string", "enum": ["family", "cost", "travel", "current_treatment",
                                                    "treatment_concern", "none"]},
        "booking_confirmed": YES_NO,
        "pain_need": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "customer_defers": YES_NO,
        "callback_agreed": YES_NO,
        "callback_time_text": STR_OR_NULL,
        "disposition": {"type": "string", "enum": list(VALID)},
        "sub_disposition": {"type": "string", "enum": sorted(set().union(*VALID.values()))},
        "lead_quality": {"type": "string", "enum": ["Not Qualified", "Not Assessable", "Low", "High", "Medium"]},
    },
}

SYSTEM_PROMPT = """You label a phone call between an enrollment agent of Aster Vale Pain Clinic (a hypothetical Indian pain clinic) and a customer who enquired about pain care, for themselves or a family member. Use only the transcript. Speaker labels may be wrong; infer roles from the dialogue. Weigh the END of the call most and use the final state after corrections. Do not diagnose.

Fill the fields in order. The labels at the end must follow from the earlier fields.

Checklist fields:
- last_customer_statement: the customer's last statement about whether or when they will proceed (exact, short), or null.
- rejection_condition: only if the customer explicitly states a condition for wanting the service ('if', 'unless', 'only when', 'until') or ties a rejection to a question the agent never answered; copy their words. Anger or complaints (about price, rules, the agent) are NOT a condition. Otherwise null.
- main_blocker: the main thing standing between the customer and booking at the end of the call, judged from the whole call (it may be implied):
  family = a relative's discussion, approval or decision is still needed;
  cost = fees, concessions, insurance or payment;
  travel = distance, transport, work or clinic timing, the patient being temporarily away, or no one available to accompany the patient;
  current_treatment = the patient is currently being treated elsewhere (physiotherapy, medicines, another clinic) and wants to continue it or see its results first; this takes priority over doubts about this clinic;
  treatment_concern = doubts or unanswered questions about the treatment, procedure, injections, outcome or clinician (including insisting on a particular or senior doctor, or wanting to research the treatment first);
  none = only if a booking is confirmed or nothing stands in the way.
  If the customer raised one of these reasons and it was not resolved, choose it even if the call ends with 'I'll call you' or 'I'll see'; a plain postponement does not replace an unresolved reason.
- booking_confirmed: yes only if both sides confirm an actual consultation date AND a clock time or bounded window. An offer, a tentative plan or 'I will confirm later' is no.
- pain_need: yes, no, or unclear (unclear if the customer says it isn't pain or the condition doesn't clearly fit pain care).
- customer_defers: yes if the customer's final position puts the decision or next contact off without an agreed day or time: 'I will let you know', 'I need some time', 'let me think', 'I'll see', 'I will call you back', 'once my husband is back', 'when she returns', 'after a month or two', 'I'll research it', 'I'll check the details you send'. No if the call simply ends after the agent offers to send details or to call, without the customer putting things off, or if the call is cut off.
- callback_agreed: yes only if a future PHONE CALL at a stated day or time was proposed by one side and acknowledged by the other ('okay', 'yes', 'haan', 'theek hai'). This includes an agent saying 'I'll call you on the 22nd' or asking 'should I call next week?' and the customer agreeing, even if the agent also sends details. A day tied to an unresolved event ('next week after Dussehra', 'after Diwali', 'when she is back') is NOT a stated day: use no. A consultation slot, or only sending information, is not a callback.
- callback_time_text: if callback_agreed is yes, the exact day/time words from the PROPOSAL of the final agreed callback (for example 'tomorrow at 4', 'on the 26th', 'next week'), not from the reply that accepts it; else null. Do not calculate dates.

disposition (precedence order):
1. Invalid Lead: reliable evidence of wrong contact, no pain-care need, a test/demo call, a patient known to be under 15, or permanently outside the service area with travel and remote care refused. Distance alone is not invalid.
2. Not Interested: a final, unconditional refusal of the offer, or a request to stop calls. Requires rejection_condition to be null. A rejected date, price objection, 'let me think' or treatment elsewhere is not a refusal.
3. Appointment Scheduled: only if booking_confirmed is yes.
4. Follow-up Required: meaningful relevant discussion remains open.
5. Unable to Assess: silence, immediate disconnect, unresolved identity or unintelligible dialogue.

sub_disposition (must belong to the disposition):
- Appointment Scheduled: Clinic Visit (new in-person), Online Consultation (remote), Rescheduled (replaces an existing or missed appointment; takes precedence).
- Follow-up Required: if main_blocker is not none, the sub_disposition MUST be that blocker, even if a callback was agreed or details were sent. If several are equally primary, prefer Family Discussion, Cost Concern, Travel Constraint, Current Treatment, Treatment Concern in that order. Only when main_blocker is none: Specific Callback (callback_agreed is yes), Information Requested (the customer's own next step is to review specific information or reports the clinic will send; the agent sending addresses, locations or routine details does NOT count), Vague Deferral (customer_defers is yes), or Further Discussion (none of these).
- Not Interested: Explicit Refusal; Do Not Contact (asks to stop calling; takes precedence).
- Invalid Lead: Test Enquiry, Wrong Contact, No Pain Need, Policy Exclusion (patient under 15), Outside Service Area.
- Unable to Assess: Incomplete Conversation.

lead_quality (apply in this order): Not Qualified if Invalid Lead. Not Assessable if Unable to Assess or pain_need is unclear. Low if a valid prospect finally refuses, shows no current intent to consult (only curiosity, or 'I'll call you if I want to come'), or defers more than 30 days (for example 'a month or two'). A cost, family, travel or treatment blocker from a prospect who still intends to consult is Medium. High if pain_need is yes, there is an explicit commitment to a consultation within the next 7 days (call date counts as day 1) and main_blocker is none. Otherwise Medium. Severe pain alone never raises it.

Return JSON only."""


def extract(row):
    """Ask the model about one call. Returns (checklist + labels, token usage)."""
    client = Groq(timeout=60, max_retries=8)     # reads GROQ_API_KEY; the SDK retries rate limits and network errors
    dt = datetime.fromisoformat(row["call_started_at"])
    user = f"Call date: {dt:%Y-%m-%d} ({dt:%A})\n\nTranscript:\n{row['transcript']}"
    resp = client.chat.completions.create(
        model=MODEL, **SETTINGS,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": "labels", "strict": True, "schema": SCHEMA}},
    )
    return apply_guards(json.loads(resp.choices[0].message.content), row["transcript"]), resp.usage


def apply_guards(out, transcript):
    """Make the labels consistent with the model's own checklist answers."""
    # a final request to stop calling is Not Interested / Do Not Contact (EX5)
    customer_turns = re.findall(r"^\s*Customer\s*:\s*(.*)$", transcript, re.MULTILINE)
    if re.search(NO_CONTACT, " ".join(customer_turns[-4:]), re.IGNORECASE):
        out["disposition"], out["sub_disposition"], out["lead_quality"] = "Not Interested", "Do Not Contact", "Low"
        return out

    if out["disposition"] == "Not Interested" and out["rejection_condition"]:
        out["disposition"] = "Follow-up Required"                  # a conditional rejection is not a refusal
    if out["disposition"] == "Follow-up Required" and out["main_blocker"] != "none":
        out["sub_disposition"] = BLOCKER_SUB[out["main_blocker"]]   # the blocker owns the sub-disposition
    if out["pain_need"] == "unclear" and out["disposition"] not in ("Invalid Lead", "Unable to Assess"):
        out["lead_quality"] = "Not Assessable"
    if out["sub_disposition"] not in VALID[out["disposition"]]:       # impossible pair -> safe default
        out["sub_disposition"] = DEFAULT_SUB[out["disposition"]]
    return out


def next_call_at(out, call_started_at):
    start = datetime.fromisoformat(call_started_at).astimezone(IST)
    if out["disposition"] in NO_CALLBACK:                          # F2
        return None
    if out["callback_agreed"] == "yes" and out["callback_time_text"]:
        when = parse_time_text(out["callback_time_text"], start)   # F3-F6, F10, F11
        if when:
            return fmt(when)
    if out["disposition"] == "Appointment Scheduled":              # F8: no inferred reminder
        return None
    days = 3 if out["customer_defers"] == "yes" else 1             # F7 vague fallback / F8 other fallback
    return fmt(at_11(start.date() + timedelta(days=days)))


def to_labels(out, call_started_at):
    return {"disposition": out["disposition"], "sub_disposition": out["sub_disposition"],
            "lead_quality": out["lead_quality"], "next_call_at": next_call_at(out, call_started_at)}