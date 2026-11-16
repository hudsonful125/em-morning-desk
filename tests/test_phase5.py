"""Tests for Phase 5: drill stats (modules/stats.py) and saved brief files (modules/archive.py)."""

from datetime import date

import pytest

from modules import archive, brief, stats

TODAY = date(2026, 11, 16)


def row(day, qtype, correct, seconds):
    return {"date": day, "question_type": qtype, "correct": correct, "seconds": seconds}


HISTORY = [
    row("2026-11-05", "pnl", 0, 20), row("2026-11-05", "bps", 1, 10),     # last week: avg 15s
    row("2026-11-14", "pnl", 1, 8),                                       # this week...
    row("2026-11-15", "inverse", 0, 12), row("2026-11-15", "bps", 1, 4),
    row("2026-11-16", "pnl", 1, 6),                                       # ...avg 7.5s
]


# --- stats ------------------------------------------------------------------------

def test_by_type_weakest_first():
    rows = stats.by_type(HISTORY)
    assert rows[0]["type"] == "inverse" and rows[0]["accuracy"] == 0
    pnl = next(r for r in rows if r["type"] == "pnl")
    assert pnl["count"] == 3 and pnl["accuracy"] == pytest.approx(2 / 3)
    assert pnl["name"] == "P&L"


def test_speed_trend_faster():
    s = stats.speed_trend(HISTORY, today=TODAY)
    assert s["this_week"] == pytest.approx(7.5)
    assert s["last_week"] == pytest.approx(15)
    assert s["arrow"] == "↑ faster"


def test_speed_trend_needs_two_weeks():
    assert stats.speed_trend(HISTORY[2:], today=TODAY)["arrow"] == ""


def test_streak_counts_consecutive_days():
    assert stats.streak(HISTORY, today=TODAY) == 3          # 14th, 15th, 16th


def test_streak_survives_until_you_drill_today():
    assert stats.streak(HISTORY[:-1], today=TODAY) == 2     # not done today yet: 14th, 15th


def test_streak_broken():
    assert stats.streak(HISTORY, today=date(2026, 11, 20)) == 0


def test_by_day():
    days = stats.by_day(HISTORY, last_n=2)
    assert days == [{"date": "2026-11-15", "right": 1, "count": 2},
                    {"date": "2026-11-16", "right": 1, "count": 1}]


# --- saved brief files ---------------------------------------------------------------

FX_ROWS = [
    {"pair": "USD/BRL", "rate": 5.7368, "prev_close": 5.6619, "pct_change": 1.3229},
    {"pair": "USD/INR", "rate": 93.9158, "prev_close": 94.2520, "pct_change": -0.3567},
]
HEADLINES = [
    {"headline": "Brazil real slumps", "source": "Reuters", "sentiment": "negative",
     "url": "https://example.com/a"},
    {"headline": "Rupee gains", "source": "Bloomberg", "sentiment": "positive"},
]


def test_brief_markdown_has_all_sections():
    summary = brief.build_summary(FX_ROWS, HEADLINES)
    md = archive.brief_markdown("2026-11-16", summary, HEADLINES, "The real weakened 1.32%.")
    assert md.startswith("# EM Morning Desk: 2026-11-16")
    assert "## Top movers" in md and "weakened 1.32%" in md
    assert "[Brazil real slumps](https://example.com/a)" in md
    assert "**positive**: Rupee gains (Bloomberg)" in md
    assert "## The brief\nThe real weakened 1.32%." in md


def test_save_brief_file(tmp_path):
    summary = brief.build_summary(FX_ROWS, [])
    path = archive.save_brief_file("2026-11-16", summary, [], "Quiet day.", folder=tmp_path / "briefs")
    text = open(path, encoding="utf-8").read()
    assert path.endswith("2026-11-16.md")
    assert "No matching headlines today." in text and "Quiet day." in text
