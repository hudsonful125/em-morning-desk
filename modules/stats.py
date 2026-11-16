"""
modules/stats.py: your drill history, for `python3 main.py --stats`.

Everything comes from the drill_results table in desk.db. Each row is one answered
question: {date, question_type, correct (1 or 0), seconds}.

Three things it works out:
  by type   accuracy and average time for each kind of question
  speed     average seconds per question, last 7 days vs the 7 days before
  streak    how many days in a row you've done the drill
"""

from datetime import date, timedelta

from modules import drill


def by_type(history):
    """
    One row per question type, weakest first.
    Returns a list of {type, name, count, accuracy, avg_seconds}.
    """
    stats = drill.type_stats(history)
    rows = []
    for qtype, s in stats.items():
        rows.append({
            "type": qtype,
            "name": drill.NICE_NAMES.get(qtype, qtype),
            "count": s["count"],
            "accuracy": s["accuracy"],
            "avg_seconds": s["avg_seconds"],
        })
    rows.sort(key=lambda r: (r["accuracy"], -r["avg_seconds"]))
    return rows


def average_seconds(rows):
    """Average seconds per question, or None if there are no rows."""
    return sum(r["seconds"] for r in rows) / len(rows) if rows else None


def speed_trend(history, today=None):
    """
    Compare your speed this week with last week.
    Returns {this_week, last_week, arrow}: arrow is "↑ faster", "↓ slower", "→ same" or "".
    """
    today = today or date.today()
    week_start = (today - timedelta(days=6)).isoformat()
    prev_start = (today - timedelta(days=13)).isoformat()

    this_week = average_seconds([r for r in history if r["date"] >= week_start])
    last_week = average_seconds([r for r in history if prev_start <= r["date"] < week_start])

    if this_week is None or last_week is None:
        arrow = ""
    elif this_week < last_week:
        arrow = "↑ faster"       # fewer seconds = faster = better
    elif this_week > last_week:
        arrow = "↓ slower"
    else:
        arrow = "→ same"
    return {"this_week": this_week, "last_week": last_week, "arrow": arrow}


def streak(history, today=None):
    """
    Days in a row with at least one drill answer.
    The streak still counts if you haven't drilled YET today but did yesterday.
    """
    today = today or date.today()
    days = {r["date"] for r in history}

    day = today if today.isoformat() in days else today - timedelta(days=1)
    count = 0
    while day.isoformat() in days:
        count += 1
        day -= timedelta(days=1)
    return count


def by_day(history, last_n=7):
    """Score per day for the most recent days you drilled: [{date, right, count}], oldest first."""
    days = {}
    for r in history:
        d = days.setdefault(r["date"], {"date": r["date"], "right": 0, "count": 0})
        d["right"] += r["correct"]
        d["count"] += 1
    return [days[d] for d in sorted(days)][-last_n:]
