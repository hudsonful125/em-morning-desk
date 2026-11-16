"""Tests for modules/drill.py. Fixed random seeds and fake input, so no typing needed."""

import random
from datetime import date

import pytest

import db
from modules import drill

FX_ROWS = [
    {"pair": "USD/BRL", "rate": 5.7368, "prev_close": 5.6619, "pct_change": 1.3229},
    {"pair": "USD/MXN", "rate": 18.6319, "prev_close": 18.5431, "pct_change": 0.4789},
    {"pair": "USD/ZAR", "rate": 16.9496, "prev_close": 16.9272, "pct_change": 0.1323},
    {"pair": "USD/KRW", "rate": 1335.4719, "prev_close": 1336.0431, "pct_change": -0.0428},
]
BIG_MAC = {"USD": 6.22, "BRL": 23.9, "MXN": 109.0, "ZAR": 56.9, "KRW": 5700.0}


# --- reading what you type ------------------------------------------------------

@pytest.mark.parametrize("typed, expected", [
    ("0.48", 0.48), ("0.48%", 0.48), ("$4.17", 4.17), ("20,000", 20000),
    ("20k", 20000), ("1.5m", 1_500_000), ("-1.2", -1.2), ("132 bps", 132),
    ("abc", None), ("", None),
])
def test_parse_answer(typed, expected):
    assert drill.parse_answer(typed) == expected


# --- grading --------------------------------------------------------------------

def test_relative_tolerance():
    assert drill.is_correct("conversion", 4.15, 4.166)      # within 1%
    assert not drill.is_correct("conversion", 4.00, 4.166)


def test_absolute_tolerance():
    assert drill.is_correct("pct_change", 0.47, 0.485)
    assert not drill.is_correct("pct_change", 0.40, 0.485)
    assert drill.is_correct("bps", 133, 132)
    assert not drill.is_correct("bps", -132, 132)


def test_unreadable_answer_is_wrong():
    assert not drill.is_correct("pnl", None, 20000)


# --- question templates: answers come from the numbers shown -----------------------

def test_pct_change_uses_shown_numbers():
    q = drill.q_pct_change([FX_ROWS[1]], random.Random(1))
    assert q["question"] == "USD/MXN moved from 18.54 to 18.63. % change?"
    assert q["answer"] == pytest.approx((18.63 - 18.54) / 18.54 * 100)


def test_conversion_uses_big_mac_price():
    q = drill.q_conversion([FX_ROWS[0]], random.Random(1), BIG_MAC)
    assert "Big Mac costs 23.90 BRL" in q["question"]
    assert q["answer"] == pytest.approx(23.9 / 5.74)


def test_inverse():
    q = drill.q_inverse([FX_ROWS[0]], random.Random(3))
    assert q["question"].startswith("USD/BRL is 5.74. What's BRL/USD?")
    assert q["answer"] == pytest.approx(1 / 5.74)


def test_pnl_long_position():
    q = drill.q_pnl([FX_ROWS[2]], random.Random(1))
    # long $1M USD/ZAR from 16.93 to 16.95 -> +20,000 ZAR
    assert "at 16.93; it moves to 16.95" in q["question"]
    assert q["answer"] == pytest.approx(20_000)


def test_bps_from_policy_rate_or_data():
    for seed in range(20):
        q = drill.q_bps(FX_ROWS, random.Random(seed))
        assert q["answer"] == pytest.approx(round(q["answer"]))  # always a whole number of bps


def test_every_template_runs():
    rng = random.Random(0)
    for make in drill.TEMPLATES.values():
        q = make(FX_ROWS, rng, BIG_MAC)
        assert q["question"] and isinstance(q["answer"], float)


# --- adaptive choice --------------------------------------------------------------

def test_weights_favour_missed_and_slow_types():
    history = (
        [{"question_type": "inverse", "correct": 0, "seconds": 20}] * 4
        + [{"question_type": "arithmetic", "correct": 1, "seconds": 4}] * 4
    )
    w = drill.type_weights(history)
    assert w["inverse"] > w["arithmetic"]
    assert w["arithmetic"] == pytest.approx(1.0)
    assert w["pnl"] == 1.5  # never seen yet


def test_choose_types_respects_cap():
    weights = {t: 1 for t in drill.QUESTION_TYPES}
    weights["inverse"] = 100
    types = drill.choose_types(7, weights, random.Random(0))
    assert len(types) == 7 and types.count("inverse") == 3


def test_make_questions_count():
    qs = drill.make_questions(FX_ROWS, [], BIG_MAC, n=5, rng=random.Random(2))
    assert len(qs) == 5


# --- running and scoring -----------------------------------------------------------

def test_run_drill_with_fake_typing_and_clock():
    qs = [drill.q_arithmetic(FX_ROWS, random.Random(5)) for _ in range(2)]
    answers = iter([str(qs[0]["answer"]), "nope"])
    ticks = iter([0, 3, 10, 18])
    said = []
    results = drill.run_drill(qs, ask=lambda _: next(answers), say=said.append, clock=lambda: next(ticks))
    assert [r["correct"] for r in results] == [True, False]
    assert [r["seconds"] for r in results] == [3, 8]
    assert "Answer:" in said[1]


def test_quit_stops_early():
    qs = [drill.q_arithmetic(FX_ROWS, random.Random(5)) for _ in range(3)]
    results = drill.run_drill(qs, ask=lambda _: "q", say=lambda _: None)
    assert results == []


def test_summary_trend_and_weakest():
    today = date(2026, 11, 16)
    history = (
        [{"date": "2026-11-05", "question_type": "pnl", "correct": 0, "seconds": 10}] * 2   # last week: 0%
        + [{"date": "2026-11-16", "question_type": "pnl", "correct": 1, "seconds": 5},
           {"date": "2026-11-16", "question_type": "inverse", "correct": 0, "seconds": 12}]
    )
    today_results = [{"correct": True, "seconds": 5}, {"correct": False, "seconds": 12}]
    s = drill.summary(today_results, history, today=today)
    assert (s["score"], s["count"]) == (1, 2)
    assert s["avg_seconds"] == pytest.approx(8.5)
    assert s["accuracy_7d"] == pytest.approx(0.5) and s["trend"] == "↑"
    assert s["weakest"] == "inverse"


def test_results_saved_and_loaded(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    q = drill.q_arithmetic(FX_ROWS, random.Random(1))
    db.save_drill_result(conn, "2026-11-16", dict(q, your_answer="5", correct=False, seconds=4.2))
    rows = db.load_drill_results(conn)
    assert len(rows) == 1 and rows[0]["question_type"] == "arithmetic" and rows[0]["correct"] == 0
    assert db.load_drill_results(conn, since_date="2026-11-17") == []
