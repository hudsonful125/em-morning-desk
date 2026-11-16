"""
modules/drill.py: a timed mental-math drill built from THIS MORNING's real numbers.

Six kinds of questions, the bread and butter of a trading desk:
  pct_change   USD/MXN moved from 18.54 to 18.63. % change?
  conversion   A Big Mac costs 325 TRY. At today's rate, what is that in USD?
  bps          USD/BRL rose 1.32% today. How many basis points is that?
  inverse      USD/BRL is 5.74. What's BRL/USD?
  pnl          You're long $1M of USD/ZAR at 16.93; it moves to 16.95. P&L in ZAR?
  arithmetic   What's 7% of 340?

Every answer is calculated in Python from the SAME rounded numbers shown in the
question, so you're never marked wrong because of hidden decimals.

Adaptive: question types you get wrong or answer slowly show up more often.
"""

import random
import time
from datetime import date, timedelta

import config

QUESTION_TYPES = ["pct_change", "conversion", "bps", "inverse", "pnl", "arithmetic"]

NICE_NAMES = {
    "pct_change": "% changes",
    "conversion": "currency conversions",
    "bps": "basis points",
    "inverse": "inverse quotes",
    "pnl": "P&L",
    "arithmetic": "quick arithmetic",
}

# How close an answer must be to count as right.
#   ("relative", 0.01) = within 1% of the right answer
#   ("absolute", 0.02) = within 0.02 of the right answer
TOLERANCE = {
    "pct_change": ("absolute", 0.02),   # % points: 0.48 or 0.49 both fine for 0.485
    "conversion": ("relative", 0.01),
    "bps": ("absolute", 1),             # 132 or 133 both fine for 132.3
    "inverse": ("relative", 0.01),
    "pnl": ("relative", 0.01),
    "arithmetic": ("relative", 0.01),
}

# Pairs with "small" prices (single or double digits) make better mental math
EASY_PAIRS = ["USD/BRL", "USD/MXN", "USD/ZAR", "USD/TRY", "USD/CNY"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def decimals_for(rate):
    """Show big rates with fewer decimals: 5.7368 -> 2 dp, 1335.47 -> 0 dp."""
    if rate >= 1000:
        return 0
    if rate >= 100:
        return 1
    return 2


def rounded(rate):
    return round(rate, decimals_for(rate))


def fmt(x, dp=None):
    """Format a number with thousands commas and dp decimals."""
    dp = decimals_for(x) if dp is None else dp
    return f"{x:,.{dp}f}"


def parse_answer(text):
    """
    Turn what you typed into a number. Accepts things like:
    "0.48", "0.48%", "$4.17", "20,000", "20k", "1.5m", "-1.2"
    Returns None if it can't be read.
    """
    if text is None:
        return None
    t = text.strip().lower().replace(",", "").replace("$", "").replace("%", "").replace(" ", "")
    t = t.replace("bps", "").replace("bp", "")
    multiplier = 1
    if t.endswith("k"):
        multiplier, t = 1_000, t[:-1]
    elif t.endswith("m"):
        multiplier, t = 1_000_000, t[:-1]
    try:
        return float(t) * multiplier
    except ValueError:
        return None


def is_correct(qtype, given, answer):
    """True if `given` is within the tolerance for this question type."""
    if given is None:
        return False
    kind, tol = TOLERANCE[qtype]
    if kind == "absolute":
        return abs(given - answer) <= tol
    return abs(given - answer) <= abs(answer) * tol


# ---------------------------------------------------------------------------
# Question templates. Each returns a dict: type, question, answer, unit, how
# ---------------------------------------------------------------------------

def q_pct_change(fx_rows, rng, prices=None):
    row = pick_row(fx_rows, rng)
    old, new = rounded(row["prev_close"]), rounded(row["rate"])
    if old == new:  # tiny move vanished in rounding: show one more decimal
        dp = decimals_for(row["rate"]) + 2
        old, new = round(row["prev_close"], dp), round(row["rate"], dp)
    else:
        dp = None
    answer = (new - old) / old * 100
    return {
        "type": "pct_change",
        "question": f"{row['pair']} moved from {fmt(old, dp)} to {fmt(new, dp)}. % change?",
        "answer": answer,
        "unit": "%",
        "how": f"(new - old) / old x 100 = ({fmt(new, dp)} - {fmt(old, dp)}) / {fmt(old, dp)} x 100",
    }


def q_conversion(fx_rows, rng, prices=None):
    row = pick_row(fx_rows, rng)
    code = row["pair"].split("/")[1]
    rate = rounded(row["rate"])
    if prices and code in prices:
        local = prices[code]
        thing = f"A Big Mac costs {fmt(local, 2 if local < 100 else 0)} {code}"
    else:
        local = rng.choice([100, 250, 500, 1000]) * (100 if rate > 100 else 1)
        thing = f"Something costs {fmt(local, 0)} {code}"
    answer = local / rate
    return {
        "type": "conversion",
        "question": f"{thing}. At today's {row['pair']} of {fmt(rate)}, what is that in USD?",
        "answer": answer,
        "unit": "$",
        "how": f"local price / USD rate = {fmt(local, 2)} / {fmt(rate)}",
    }


def q_bps(fx_rows, rng, prices=None):
    if rng.random() < 0.5:
        # From today's data: express a % move in basis points
        row = max(fx_rows, key=lambda r: abs(r["pct_change"]))
        pct = round(row["pct_change"], 2)
        direction = "rose" if pct > 0 else "fell"
        return {
            "type": "bps",
            "question": f"{row['pair']} {direction} {abs(pct):.2f}% today. How many basis points is that?",
            "answer": abs(pct) * 100,
            "unit": "bps",
            "how": "1% = 100 basis points, so multiply the % by 100",
        }
    # Central-bank style: a policy rate change
    start = rng.choice([4.25, 5.50, 6.75, 7.00, 10.50, 11.25, 13.75])
    step = rng.choice([0.25, 0.50, 0.75, 1.00])
    end = start + step if rng.random() < 0.5 else start - step
    return {
        "type": "bps",
        "question": f"A central bank moved its policy rate from {start:.2f}% to {end:.2f}%. "
                    f"How many basis points? (use a minus sign for a cut)",
        "answer": (end - start) * 100,
        "unit": "bps",
        "how": "difference in % x 100 = basis points",
    }


def q_inverse(fx_rows, rng, prices=None):
    row = pick_row(fx_rows, rng, easy=True)
    rate = rounded(row["rate"])
    code = row["pair"].split("/")[1]
    answer = 1 / rate
    return {
        "type": "inverse",
        "question": f"{row['pair']} is {fmt(rate)}. What's {code}/USD? (4 decimals)",
        "answer": answer,
        "unit": "",
        "how": f"1 / {fmt(rate)}",
    }


def q_pnl(fx_rows, rng, prices=None):
    row = pick_row(fx_rows, rng, easy=True)
    code = row["pair"].split("/")[1]
    entry, exit_ = rounded(row["prev_close"]), rounded(row["rate"])
    if entry == exit_:
        exit_ = round(entry + rng.choice([-0.05, 0.05, 0.10]), 2)
    notional = config.DRILL_PNL_NOTIONAL
    answer = notional * (exit_ - entry)
    return {
        "type": "pnl",
        "question": (f"You're long ${notional / 1_000_000:g}M of {row['pair']} at {fmt(entry, 2)}; "
                     f"it moves to {fmt(exit_, 2)}. P&L in {code}? (minus sign for a loss)"),
        "answer": answer,
        "unit": code,
        "how": f"notional x (exit - entry) = {notional:,} x ({fmt(exit_, 2)} - {fmt(entry, 2)})",
    }


def q_arithmetic(fx_rows, rng, prices=None):
    pct = rng.choice([3, 4, 6, 7, 8, 9, 12, 15, 18, 35])
    base = rng.choice([120, 240, 340, 450, 560, 780, 1250, 2400])
    return {
        "type": "arithmetic",
        "question": f"What's {pct}% of {base:,}?",
        "answer": pct / 100 * base,
        "unit": "",
        "how": f"{pct} / 100 x {base:,}",
    }


TEMPLATES = {
    "pct_change": q_pct_change,
    "conversion": q_conversion,
    "bps": q_bps,
    "inverse": q_inverse,
    "pnl": q_pnl,
    "arithmetic": q_arithmetic,
}


def pick_row(fx_rows, rng, easy=False):
    """Pick a random FX row; easy=True prefers pairs with small prices."""
    if easy:
        easy_rows = [r for r in fx_rows if r["pair"] in EASY_PAIRS]
        if easy_rows:
            return rng.choice(easy_rows)
    return rng.choice(fx_rows)


# ---------------------------------------------------------------------------
# Adaptive choice of question types
# ---------------------------------------------------------------------------

def type_weights(history):
    """
    Look at past results and give each question type a weight.
    Base weight 1, plus up to +2 for a high miss rate, plus up to +1 for being slow.
    Types you've never seen get a small bonus so everything gets practised.
    """
    stats = type_stats(history)
    all_times = [r["seconds"] for r in history]
    overall_avg = sum(all_times) / len(all_times) if all_times else 0

    weights = {}
    for qtype in QUESTION_TYPES:
        s = stats.get(qtype)
        if not s:
            weights[qtype] = 1.5
            continue
        miss_rate = 1 - s["accuracy"]
        slowness = 0.0
        if overall_avg > 0:
            slowness = min(max(s["avg_seconds"] / overall_avg - 1, 0), 1)
        weights[qtype] = 1 + 2 * miss_rate + slowness
    return weights


def type_stats(history):
    """Accuracy and average time per question type: {type: {count, accuracy, avg_seconds}}."""
    stats = {}
    for r in history:
        s = stats.setdefault(r["question_type"], {"count": 0, "right": 0, "seconds": 0.0})
        s["count"] += 1
        s["right"] += r["correct"]
        s["seconds"] += r["seconds"]
    for s in stats.values():
        s["accuracy"] = s["right"] / s["count"]
        s["avg_seconds"] = s["seconds"] / s["count"]
    return stats


def choose_types(n, weights, rng, max_per_type=3):
    """Pick n question types using the weights, with at most max_per_type of any one type."""
    chosen = []
    counts = {t: 0 for t in QUESTION_TYPES}
    while len(chosen) < n:
        available = [t for t in QUESTION_TYPES if counts[t] < max_per_type]
        pick = rng.choices(available, weights=[weights[t] for t in available])[0]
        chosen.append(pick)
        counts[pick] += 1
    return chosen


def make_questions(fx_rows, history, prices=None, n=None, rng=None):
    """Build today's list of questions."""
    rng = rng or random.Random()
    n = n or config.DRILL_QUESTIONS
    types = choose_types(n, type_weights(history), rng)
    return [TEMPLATES[t](fx_rows, rng, prices) for t in types]


# ---------------------------------------------------------------------------
# Running the drill
# ---------------------------------------------------------------------------

def show_answer(q):
    """The right answer, formatted sensibly for its type."""
    a = q["answer"]
    if q["type"] == "inverse":
        return f"{a:.4f}"
    if q["type"] == "conversion":
        return f"${a:,.2f}"
    if q["type"] == "pct_change":
        return f"{a:+.2f}%"
    if q["type"] == "bps":
        return f"{a:,.0f} bps"
    if q["type"] == "pnl":
        return f"{a:+,.0f} {q['unit']}"
    return f"{a:,.2f}".rstrip("0").rstrip(".")


def run_drill(questions, ask=input, say=print, clock=time.monotonic):
    """
    Ask each question, time it, grade it. Returns a list of result dicts.
    `ask`, `say` and `clock` can be swapped out by tests.
    Type q to stop early; a blank answer counts as wrong.
    """
    results = []
    for i, q in enumerate(questions, start=1):
        start = clock()
        typed = ask(f"Q{i}. {q['question']} > ")
        seconds = clock() - start
        if typed.strip().lower() in ("q", "quit", "exit"):
            say("Stopping the drill early.")
            break
        given = parse_answer(typed)
        correct = is_correct(q["type"], given, q["answer"])
        if correct:
            say(f"   ✅ Correct ({show_answer(q)}) in {seconds:.1f}s")
        else:
            say(f"   ❌ Answer: {show_answer(q)}   How: {q['how']}")
        results.append(dict(q, your_answer=typed.strip(), correct=correct, seconds=seconds))
    return results


# ---------------------------------------------------------------------------
# The end-of-drill summary
# ---------------------------------------------------------------------------

def accuracy(rows):
    return sum(r["correct"] for r in rows) / len(rows) if rows else None


def summary(today_results, history, today=None):
    """
    Numbers for the end-of-drill report.
    history = all saved rows INCLUDING today's (as dicts with date, question_type, correct, seconds).
    """
    today = today or date.today()
    last7_start = (today - timedelta(days=6)).isoformat()
    prev7_start = (today - timedelta(days=13)).isoformat()

    last7 = [r for r in history if r["date"] >= last7_start]
    prev7 = [r for r in history if prev7_start <= r["date"] < last7_start]
    acc7, acc_prev = accuracy(last7), accuracy(prev7)
    if acc7 is None or acc_prev is None:
        trend = ""
    elif acc7 > acc_prev:
        trend = "↑"
    elif acc7 < acc_prev:
        trend = "↓"
    else:
        trend = "→"

    # Weakest area: lowest accuracy over the last 30 answers (ties: slower one)
    recent = history[-30:]
    stats = type_stats(recent)
    weakest = None
    if stats:
        weakest = min(stats, key=lambda t: (stats[t]["accuracy"], -stats[t]["avg_seconds"]))

    n = len(today_results)
    return {
        "score": sum(r["correct"] for r in today_results),
        "count": n,
        "avg_seconds": sum(r["seconds"] for r in today_results) / n if n else 0,
        "total_seconds": sum(r["seconds"] for r in today_results),
        "accuracy_7d": acc7,
        "trend": trend,
        "weakest": weakest,
    }
