"""Turn the callback words the model returns into an exact date and time.

Example: a call on 2026-10-14 at 13:19, words "tomorrow evening" -> 2026-10-15 18:00 (IST).
The rules come from the Label Rules sheet (F4, F5, F6, F10, F11).
"""
import re
import calendar
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAYPART_HOURS = {"morning": 10, "afternoon": 15, "evening": 18, "lunch": 13, "noon": 12}   # F5
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
NUMBER = r"(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def fmt(dt):
    """Datetime -> '2026-10-15T18:00:00+05:30' (seconds, no microseconds)."""
    return dt.replace(microsecond=0).isoformat(timespec="seconds")

def at_11(day):
    """A calendar date at 11:00 IST (the default time when only a day is known)."""
    return datetime.combine(day, time(11, 0), tzinfo=IST)

def to_number(word):
    return int(word) if word.isdigit() else NUMBER_WORDS[word]

def add_one_month(d):
    """Same day next month; 31 Jan -> 28/29 Feb (F11)."""
    year, month = d.year, d.month + 1
    if month == 13:
        year, month = year + 1, 1
    last_day = calendar.monthrange(year, month)[1]
    return d.replace(year=year, month=month, day=min(d.day, last_day))


def find_clock_time(t):
    """Return (hour, minute) in 24-hour form, or None if no clock time is mentioned."""
    t = re.sub(r"\b\d{1,2}(?:st|nd|rd|th)\b", " ", t)          # '25th' is a date, not a time

    # explicit am/pm: '4 pm', '4:30pm', '9 a.m.'
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        hour = hour % 12 + (12 if m.group(3) == "p" else 0)    # 12 am -> 0, 12 pm -> 12, 4 pm -> 16
        return valid(hour, minute)

    # no am/pm: '16:00', 'at 4', '4 o'clock'
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"\b(?:at|around|by|after)\s+(\d{1,2})\b", t) or re.search(r"\b(\d{1,2})\s*o'?clock\b", t)
        if not m:
            return None
        hour, minute = int(m.group(1)), 0

    # decide AM/PM (F5)
    if any(word in t for word in ("afternoon", "evening", "lunch")):
        if hour < 12:
            hour += 12                                          # 'evening at 6' -> 18
    elif "morning" not in t and 1 <= hour <= 7:
        hour += 12                                              # 1-7 without am/pm means PM
    return valid(hour, minute)

def valid(hour, minute):
    """Reject impossible times such as '25:00' instead of crashing."""
    return (hour, minute) if 0 <= hour < 24 and 0 <= minute < 60 else None

def find_daypart_hour(t):
    """'morning' -> 10, 'evening' -> 18, ... or None (F5)."""
    for word, hour in DAYPART_HOURS.items():
        if word in t:
            return hour
    return None


def find_explicit_date(t, d):
    """'26th', 'on the 26', '26 October', 'Oct 26' -> the next such date on or after d (F6)."""
    month = None
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]{3})[a-z]*\b", t)       # '26 October'
    if m and m.group(2) in MONTHS:
        day_num, month = int(m.group(1)), MONTHS[m.group(2)]
    else:
        m = re.search(r"\b([a-z]{3})[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b", t)             # 'Oct 26'
        if m and m.group(1) in MONTHS:
            day_num, month = int(m.group(2)), MONTHS[m.group(1)]
        else:
            m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b|\bthe\s+(\d{1,2})\b", t)          # '26th', 'the 26'
            if not m:
                return None
            day_num = int(m.group(1) or m.group(2))

    year = d.year
    if month is None:                     # day only: this month, or next month if that day has passed
        month = d.month
        if day_num < d.day:
            month += 1
            if month == 13:
                year, month = year + 1, 1
    elif (month, day_num) < (d.month, d.day):
        year += 1                         # month and day without a year: next future occurrence
    try:
        return d.replace(year=year, month=month, day=day_num)
    except ValueError:                    # e.g. 31 November
        return None

def find_weekday(t, d):
    """'Friday', 'this Friday', 'next Friday' -> a date, or None (F4)."""
    for i, name in enumerate(WEEKDAYS):
        if not re.search(rf"\b{name}\b", t):
            continue
        days_ahead = (i - d.weekday()) % 7                      # 0 if today is that weekday
        if re.search(rf"\bnext {name}\b", t):                   # that day in the following Mon-Sun week
            monday_this_week = d - timedelta(days=d.weekday())
            return monday_this_week + timedelta(days=7 + i)
        if re.search(rf"\bthis {name}\b", t):                   # today counts
            return d + timedelta(days=days_ahead)
        if days_ahead == 0:                                     # plain weekday: strictly in the future
            days_ahead = 7
        return d + timedelta(days=days_ahead)
    return None

def find_day(t, d):
    """The calendar day the words refer to, or None. Checked in this order (the order matters)."""
    m = re.search(rf"\b(?:in|after)\s+{NUMBER}\s+(day|week|month)s?\b", t)
    if m:
        n, unit = to_number(m.group(1)), m.group(2)
        if unit == "day":
            return d + timedelta(days=n)
        if unit == "week":
            return d + timedelta(weeks=n)
        return add_one_month(d)                                 # F11
    if re.search(r"day after tomorrow|parso", t):              # before 'tomorrow'
        return d + timedelta(days=2)
    if re.search(r"\b(tomorrow|tmrw)\b", t):
        return d + timedelta(days=1)
    if re.search(r"\b(today|tonight)\b|\bthis (morning|afternoon|evening)\b", t):
        return d
    if re.search(r"\bnext month\b", t):
        return add_one_month(d).replace(day=1)                  # F11: first day of next month
    if re.search(r"\bnext week\b", t):
        return d + timedelta(days=7 - d.weekday())              # F4: next Monday
    explicit = find_explicit_date(t, d)
    if explicit is not None:
        return explicit
    return find_weekday(t, d)


def parse_time_text(text, start):
    """Callback words + call start time -> exact IST datetime, or None if not understood or in the past."""
    t = text.lower()
    t = re.sub(rf"^\s*{NUMBER}\s+(min|minute|hour)", r"in \1 \2", t)     # '15 minutes' -> 'in 15 minutes'

    # 'in 15 minutes' / 'in 2 hours': exact offset from the call start, seconds kept (F10)
    m = re.search(rf"\b(?:in|after)\s+{NUMBER}\s+(minute|min|hour|day|week|month)s?\b", t)
    if m and m.group(2) in ("minute", "min"):
        return start + timedelta(minutes=to_number(m.group(1)))
    if m and m.group(2) == "hour":
        return start + timedelta(hours=to_number(m.group(1)))

    day = find_day(t, start.date())
    clock = find_clock_time(t)

    if day is None:
        if clock is None:
            return None                                         # nothing we understand
        today = datetime.combine(start.date(), time(*clock), tzinfo=IST)
        return today if today > start else today + timedelta(days=1)    # F5: time only

    if clock is not None:
        hour, minute = clock
    elif find_daypart_hour(t) is not None:
        hour, minute = find_daypart_hour(t), 0
    else:
        hour, minute = 11, 0                                    # F5: day with no time
    result = datetime.combine(day, time(hour, minute), tzinfo=IST)
    return result if result > start else None                  # F6: never repair a past time