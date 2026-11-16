"""Tests for data/news.py. Uses a saved sample Finnhub reply, so no API calls."""

import json
from pathlib import Path

import db
from data import news

FIXTURE = Path(__file__).parent / "fixtures" / "finnhub_news_forex.json"


def load_items():
    return news.parse_news(json.loads(FIXTURE.read_text()), "forex")


def test_parse_skips_malformed_stories():
    items = load_items()
    assert len(items) == 5
    assert items[0]["headline"] == "Brazil real slumps as fiscal worries mount"
    assert items[0]["published"] == 1794826800


def test_keywords_match_whole_words_only():
    assert news.matched_keywords("Fed holds rates") == ["Fed"]
    assert news.matched_keywords("Fedora sales jump") == []
    assert news.matched_keywords("Brazil and the central bank") == ["Brazil", "central bank"]


def test_sentiment_scores():
    assert news.sentiment("Rupee gains after RBI steps in") == ("positive", 1)
    assert news.sentiment("Brazil real slumps as fiscal worries mount") == ("negative", -2)
    assert news.sentiment("Fed's Powell speaks on Thursday") == ("neutral", 0)


def test_pick_relevant_filters_and_dedupes():
    picked = news.pick_relevant(load_items())
    headlines = [p["headline"] for p in picked]
    # The tech-stocks story has no tracked keyword; the Brazil story appears twice
    assert headlines == [
        "Brazil real slumps as fiscal worries mount",
        "Rupee gains after RBI steps in",
        "Fed's Powell speaks on Thursday",
    ]
    assert picked[0]["sentiment"] == "negative"


def test_pick_relevant_respects_limit():
    assert len(news.pick_relevant(load_items(), limit=2)) == 2


def test_cached_news_spends_no_api_calls(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "test.db")
    db.save_news(conn, "2026-11-16", load_items())

    def fail_if_called(*args, **kwargs):
        raise AssertionError("API was called even though news was cached")

    monkeypatch.setattr(news, "fetch_news", fail_if_called)
    picked, warnings = news.get_news(conn, "2026-11-16", api_key="fake")
    assert len(picked) == 3 and warnings == []


def test_missing_key_gives_clear_warning(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    picked, warnings = news.get_news(conn, "2026-11-16", api_key=None)
    assert picked == [] and "FINNHUB_KEY" in warnings[0]
