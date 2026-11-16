"""
Tests for data/fx.py and db.py. Run all tests with:  pytest
These use a saved sample reply (tests/fixtures/), so they spend no API credits.
"""

import json
from pathlib import Path

import pytest

import db
from data import fx

FIXTURE = Path(__file__).parent / "fixtures" / "twelve_data_quote_batch.json"


def test_pct_change_up():
    assert fx.pct_change(5.40, 5.00) == pytest.approx(8.0)


def test_pct_change_down():
    # USD/MXN from 17.55 to 17.20 is about a -1.99% move
    assert fx.pct_change(17.20, 17.55) == pytest.approx(-1.9943, abs=1e-4)


def test_direction_word():
    assert fx.direction_word(1.2) == "weaker"     # USD/XXX up -> local currency weaker
    assert fx.direction_word(-0.5) == "stronger"
    assert fx.direction_word(0) == "flat"


def test_chunk_respects_rate_limit_size():
    assert fx.chunk(list(range(10)), 8) == [list(range(8)), [8, 9]]


def test_parse_batch_reply_with_one_failed_symbol():
    data = json.loads(FIXTURE.read_text())
    rows, errors = fx.parse_quotes(data, ["USD/BRL", "USD/MXN", "USD/TRY"])

    assert [r["pair"] for r in rows] == ["USD/BRL", "USD/MXN"]
    brl = rows[0]
    assert brl["rate"] == pytest.approx(5.64778)
    assert brl["prev_close"] == pytest.approx(5.56145)
    # Our own Python math should match the percent_change Twelve Data reports (1.55229%)
    assert brl["pct_change"] == pytest.approx(1.55229, abs=1e-3)

    assert len(errors) == 1 and "USD/TRY" in errors[0]


def test_parse_single_symbol_reply():
    # With one symbol, Twelve Data returns the quote itself rather than a dict of quotes.
    single = json.loads(FIXTURE.read_text())["USD/BRL"]
    rows, errors = fx.parse_quotes(single, ["USD/BRL"])
    assert len(rows) == 1 and not errors


def test_sort_by_biggest_move():
    rows = [
        {"pair": "A", "pct_change": 0.3},
        {"pair": "B", "pct_change": -1.5},
        {"pair": "C", "pct_change": 0.9},
    ]
    assert [r["pair"] for r in fx.sort_by_biggest_move(rows)] == ["B", "C", "A"]


def test_save_and_load_round_trip(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    rows = [{"pair": "USD/ZAR", "rate": 18.25, "prev_close": 18.40, "pct_change": -0.815}]
    db.save_fx_rates(conn, "2026-11-12", rows)
    db.save_fx_rates(conn, "2026-11-12", rows)  # saving twice must not duplicate
    assert db.load_fx_rates(conn, "2026-11-12") == rows
    assert db.load_fx_rates(conn, "2026-11-11") == []


def test_cached_day_spends_no_api_calls(tmp_path, monkeypatch):
    """If today's rates are already saved, get_fx_rates must not call the API."""
    conn = db.connect(tmp_path / "test.db")
    monkeypatch.setattr(fx.config, "CURRENCIES", [{"pair": "USD/ZAR", "country": "South Africa", "currency": "rand"}])
    db.save_fx_rates(conn, "2026-11-12", [{"pair": "USD/ZAR", "rate": 18.25, "prev_close": 18.40, "pct_change": -0.815}])

    def fail_if_called(*args, **kwargs):
        raise AssertionError("API was called even though data was cached")

    monkeypatch.setattr(fx, "fetch_quotes", fail_if_called)
    rows, warnings = fx.get_fx_rates(conn, "2026-11-12", api_key="fake")
    assert len(rows) == 1 and warnings == []
