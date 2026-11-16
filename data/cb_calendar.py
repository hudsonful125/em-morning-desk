"""
data/cb_calendar.py: upcoming central bank rate decisions, for "What to watch".

There's no free API for EM central bank calendars, so the dates live in a small CSV you
can edit: data/central_bank_calendar.csv (columns: date, country, bank, source).
  source = "official"     the date is from the central bank's own website
  source = "cbrates.com"  from cbrates.com's meeting list; check the bank's site to be sure

Collected 16 Nov 2026. Most banks publish next year's dates around December, so add 2027
rows as they come out (India, China and most 2027 dates were not yet available).
"""

import csv
import os
from datetime import date, timedelta

CALENDAR_PATH = os.path.join("data", "central_bank_calendar.csv")


def load_meetings(path=CALENDAR_PATH):
    """Read the CSV into a list of dicts sorted by date. A missing file gives an empty list."""
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("date") or "").strip()]
    return sorted(rows, key=lambda r: r["date"])


def upcoming(meetings, today=None, days=14):
    """Meetings from today up to `days` days ahead."""
    today = today or date.today()
    start, end = today.isoformat(), (today + timedelta(days=days)).isoformat()
    return [m for m in meetings if start <= m["date"] <= end]


def describe(meeting, today=None):
    """e.g. 'Brazil: Banco Central do Brasil (Copom) rate decision on Wed 09 Dec (in 23 days)'"""
    today = today or date.today()
    day = date.fromisoformat(meeting["date"])
    gap = (day - today).days
    when = "today" if gap == 0 else "tomorrow" if gap == 1 else f"in {gap} days"
    text = f"{meeting['country']}: {meeting['bank']} rate decision on {day:%a %d %b} ({when})"
    if meeting.get("source") and meeting["source"] != "official":
        text += f" [date from {meeting['source']}]"
    return text
