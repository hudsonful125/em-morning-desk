"""Tests for Phase 6: central bank calendar, extra price items, email, and the shared brief routine."""

from datetime import date

import pytest

import config
import db
from data import bigmac, cb_calendar
from modules import brief, emailer, prices, routine

TODAY = date(2026, 11, 16)

MEETINGS = [
    {"date": "2026-11-18", "country": "Indonesia", "bank": "Bank Indonesia", "source": "official"},
    {"date": "2026-11-26", "country": "South Korea", "bank": "Bank of Korea", "source": "cbrates.com"},
    {"date": "2026-12-09", "country": "Brazil", "bank": "Copom", "source": "cbrates.com"},
]


# --- central bank calendar ------------------------------------------------------------

def test_upcoming_is_next_14_days():
    assert [m["country"] for m in cb_calendar.upcoming(MEETINGS, TODAY)] == ["Indonesia", "South Korea"]


def test_describe():
    assert cb_calendar.describe(MEETINGS[0], TODAY) == \
        "Indonesia: Bank Indonesia rate decision on Wed 18 Nov (in 2 days)"
    assert cb_calendar.describe(MEETINGS[1], TODAY).endswith("(in 10 days) [date from cbrates.com]")
    assert "(tomorrow)" in cb_calendar.describe(MEETINGS[0], date(2026, 11, 17))


def test_real_calendar_file_loads_in_order():
    meetings = cb_calendar.load_meetings()
    dates = [m["date"] for m in meetings]
    assert meetings and dates == sorted(dates)
    assert all(date.fromisoformat(d) for d in dates)


def test_missing_calendar_file_is_empty(tmp_path):
    assert cb_calendar.load_meetings(tmp_path / "nope.csv") == []


def test_fact_sheet_lists_meetings():
    summary = brief.build_summary([{"pair": "USD/BRL", "rate": 5.7, "prev_close": 5.6, "pct_change": 1.8}], [])
    text = brief.summary_to_text(summary, [], ["Indonesia: Bank Indonesia rate decision on Wed 18 Nov (in 2 days)"])
    assert "Central bank rate decisions in the next 14 days:\n- Indonesia" in text
    assert "- none scheduled" in brief.summary_to_text(summary, [], [])
    assert "Central bank" not in brief.summary_to_text(summary, [])  # old callers unchanged


# --- extra price items ----------------------------------------------------------------

@pytest.mark.parametrize("item", [i for i in config.ITEMS if i["source"] != "economist"])
def test_item_files_have_a_us_price(item):
    local_prices, price_date, warnings = bigmac.get_item_prices(item)
    assert local_prices["USD"] > 0 and price_date and not warnings
    assert set(local_prices) <= {c["pair"].split("/")[1] for c in config.CURRENCIES} | {"USD"}


def test_tie_in_uses_phrase():
    fx_rows = [{"pair": "USD/BRL", "rate": 5.10, "prev_close": 5.00, "pct_change": 2.0}]
    table = prices.build_price_table(fx_rows, {"USD": 1.14, "BRL": 6.61})
    line = prices.news_tie_in(table, "Gasoline (1 liter)", "a liter of gasoline")
    assert line.startswith("The real weakened 2.00% overnight, so a liter of gasoline in Brazil got")


# --- email ----------------------------------------------------------------------------

class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def login(self, user, password):
        self.user, self.password = user, password

    def send_message(self, message):
        FakeSMTP.sent.append((self.user, self.password, message))


def test_send_email_with_fake_server():
    settings = {"address": "me@gmail.com", "password": "abcd", "to": "me@gmail.com"}
    assert emailer.send_email("Hi", "Body text", settings, smtp_class=FakeSMTP) is None
    user, password, message = FakeSMTP.sent[-1]
    assert (user, password, message["Subject"], message["To"]) == ("me@gmail.com", "abcd", "Hi", "me@gmail.com")
    assert "Body text" in message.get_content()


def test_email_skipped_without_settings(monkeypatch):
    monkeypatch.delenv("EMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("EMAIL_APP_PASSWORD", raising=False)
    assert emailer.email_settings() is None
    assert "isn't set up" in emailer.send_email("Hi", "Body")


def test_app_password_spaces_removed(monkeypatch):
    monkeypatch.setenv("EMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("EMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.delenv("EMAIL_TO", raising=False)
    assert emailer.email_settings() == {"address": "me@gmail.com", "password": "abcdefghijklmnop", "to": "me@gmail.com"}


# --- the shared brief routine (no real API calls) -----------------------------------------

def test_make_brief_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # briefs/ is written here, not in the real folder
    conn = db.connect(str(tmp_path / "test.db"))
    fx_rows = [{"pair": "USD/BRL", "rate": 5.7368, "prev_close": 5.6619, "pct_change": 1.3229}]
    monkeypatch.setattr(routine.fx, "get_fx_rates", lambda *a, **k: (fx_rows, []))
    monkeypatch.setattr(routine.news, "get_news", lambda *a, **k: ([], []))
    monkeypatch.setattr(routine, "todays_meetings", lambda today: ["Brazil: Copom rate decision on Wed 18 Nov (in 2 days)"])
    monkeypatch.setattr(routine, "price_lines", lambda rows: ["The real weakened..."])
    sheets = []
    monkeypatch.setattr(routine.brief, "write_brief", lambda sheet, key: (sheets.append(sheet) or "A quiet day.", None))

    r = routine.make_brief(conn, TODAY)
    assert r["text"] == "A quiet day." and r["error"] is None
    assert "Copom" in sheets[0]
    saved = (tmp_path / "briefs" / "2026-11-16.md").read_text(encoding="utf-8")
    assert "## Central bank decisions, next 14 days" in saved and "## Prices around the world" in saved

    # Second call the same day uses the saved brief: Claude is not asked again
    routine.make_brief(conn, TODAY)
    assert len(sheets) == 1


def test_make_brief_without_fx(tmp_path, monkeypatch):
    monkeypatch.setattr(routine.fx, "get_fx_rates", lambda *a, **k: ([], ["No key"]))
    r = routine.make_brief(db.connect(str(tmp_path / "t.db")), TODAY)
    assert r["text"] is None and "No FX data" in r["error"] and r["warnings"] == ["No key"]
