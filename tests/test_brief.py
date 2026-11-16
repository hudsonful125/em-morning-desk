"""Tests for modules/brief.py. A fake Claude client is used, so no API calls or cost."""

from types import SimpleNamespace

import db
from modules import brief

FX_ROWS = [
    {"pair": "USD/BRL", "rate": 5.7368, "prev_close": 5.6619, "pct_change": 1.3229},
    {"pair": "USD/INR", "rate": 93.9158, "prev_close": 94.2520, "pct_change": -0.3567},
    {"pair": "USD/CLP", "rate": 1001.551, "prev_close": 995.1338, "pct_change": 0.6449},
    {"pair": "USD/TRY", "rate": 50.3943, "prev_close": 50.3980, "pct_change": -0.0073},
]
HEADLINES = [
    {"headline": "Brazil real slumps as fiscal worries mount", "source": "Reuters", "sentiment": "negative"},
    {"headline": "Rupee gains after RBI steps in", "source": "Bloomberg", "sentiment": "positive"},
    {"headline": "Brazil budget vote delayed", "source": "Reuters", "sentiment": "neutral"},
]


def test_top_movers_sorted_by_size():
    summary = brief.build_summary(FX_ROWS, HEADLINES)
    assert [m["code"] for m in summary["top_movers"]] == ["BRL", "CLP", "INR"]


def test_direction_from_usd_quote():
    summary = brief.build_summary(FX_ROWS, HEADLINES)
    assert [m["code"] for m in summary["weakened"]] == ["BRL", "CLP"]
    assert [m["code"] for m in summary["strengthened"]] == ["INR", "TRY"]


def test_average_move_and_mood():
    summary = brief.build_summary(FX_ROWS, HEADLINES)
    assert abs(summary["average_move"] - (1.3229 - 0.3567 + 0.6449 - 0.0073) / 4) < 1e-9
    assert summary["mood_counts"] == {"positive": 1, "negative": 1, "neutral": 1}
    assert summary["overall_mood"] == "mixed/neutral"


def test_fact_sheet_contains_python_numbers():
    text = brief.summary_to_text(brief.build_summary(FX_ROWS, HEADLINES), HEADLINES)
    assert "Brazil real (BRL) weakened 1.32% vs USD (USD/BRL 5.6619 -> 5.7368)" in text
    assert "India rupee (INR) strengthened 0.36%" in text
    assert "[negative] Brazil real slumps" in text


def test_fact_sheet_without_headlines():
    text = brief.summary_to_text(brief.build_summary(FX_ROWS, []), [])
    assert "no headlines available" in text


class FakeClient:
    """Pretends to be anthropic.Anthropic(); records the request and returns a canned reply."""

    def __init__(self, stop_reason="end_turn", blocks=None):
        self.request = None
        reply = SimpleNamespace(
            stop_reason=stop_reason,
            content=blocks if blocks is not None else [
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text="## Overnight summary\nThe real led losses."),
            ],
        )

        def create(**kwargs):
            self.request = kwargs
            return reply

        self.beta = SimpleNamespace(messages=SimpleNamespace(create=create))


def test_write_brief_returns_only_text_blocks():
    client = FakeClient()
    text, error = brief.write_brief("FACT SHEET", api_key=None, client=client)
    assert error is None
    assert text == "## Overnight summary\nThe real led losses."
    assert client.request["messages"][0]["content"] == "FACT SHEET"
    assert "Use ONLY the numbers" in client.request["system"]


def test_write_brief_handles_refusal():
    text, error = brief.write_brief("x", api_key=None, client=FakeClient(stop_reason="refusal", blocks=[]))
    assert text is None and "declined" in error


def test_write_brief_without_key():
    text, error = brief.write_brief("x", api_key=None)
    assert text is None and "ANTHROPIC_API_KEY" in error


def test_brief_save_and_load(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    assert db.load_brief(conn, "2026-11-16") is None
    db.save_brief(conn, "2026-11-16", "hello")
    assert db.load_brief(conn, "2026-11-16") == "hello"
