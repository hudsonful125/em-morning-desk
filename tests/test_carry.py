"""Tests for the carry table, commodity links, stale-rate warnings and commodity moves."""

import math
from datetime import date

import pytest

import db
from data import commodities
from modules import brief, carry


def series(values):
    """[('2020-01-01', v0), ('2020-02-01', v1), ...] from a list of closes."""
    return [(f"{2020 + i // 12}-{i % 12 + 1:02d}-01", v) for i, v in enumerate(values)]


def zigzag(months, size):
    """Closes that go up `size`% then down back again, over and over."""
    values, v = [], 100.0
    for i in range(months + 1):
        values.append(v)
        v = v * (1 + size / 100) if i % 2 == 0 else v / (1 + size / 100)
    return series(values)


def test_stdev_and_correlation():
    assert carry.stdev([1]) is None
    assert carry.stdev([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.138, abs=0.001)
    assert carry.correlation([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert carry.correlation([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)
    assert carry.correlation([1, 1, 1], [1, 2, 3]) is None  # no movement, no answer


def test_annual_vol():
    flat = series([5.0] * 40)
    assert carry.annual_vol(flat) == 0
    assert carry.annual_vol(zigzag(40, 2)) > carry.annual_vol(zigzag(40, 1)) > 0
    assert carry.annual_vol(series([5.0])) is None


def test_carry_table_ranks_by_carry():
    rates = {"USD": 4.0, "USD/BRL": 14.0, "USD/KRW": 3.0, "USD/MXN": 7.0}
    history = {"USD/BRL": zigzag(40, 3), "USD/KRW": zigzag(40, 1), "USD/MXN": zigzag(40, 2),
               "USD/XYZ": zigzag(40, 1)}  # no policy rate, so left out
    rows = carry.carry_table(rates, history, {"USD/BRL": 6.0})
    assert [r["pair"] for r in rows] == ["USD/BRL", "USD/MXN", "USD/KRW"]
    brl = rows[0]
    assert brl["carry"] == 10.0
    assert brl["carry_to_vol"] == pytest.approx(10.0 / brl["vol"])
    assert brl["past_year"] == 4.0          # 10% carry minus the dollar's 6% gain
    assert rows[2]["carry"] == -1.0 and rows[2]["past_year"] is None


def test_commodity_links_sign():
    oil = zigzag(61, 5)
    # USD/COP falls when oil rises -> the peso rises with oil -> correlation +1
    cop = series([100 / (v / 100) for _, v in oil])
    links = carry.commodity_links({"USO": oil, "USD/COP": cop}, ["USD/COP", "USD/BRL"], ["USO", "CPER"])
    assert links == {("USD/COP", "USO"): pytest.approx(1.0)}


def test_stale_rate_warnings():
    meetings = [
        {"date": "2026-11-10", "country": "Brazil", "bank": "Copom"},        # before the check
        {"date": "2026-11-18", "country": "Indonesia", "bank": "BI"},        # day of the check
        {"date": "2026-11-20", "country": "Mars", "bank": "Mars Bank"},      # not one of ours
        {"date": "2026-11-25", "country": "Brazil", "bank": "Copom"},        # still to come
    ]
    pairs = {"Brazil": "USD/BRL", "Indonesia": "USD/IDR"}
    warnings = carry.stale_rate_warnings("2026-11-18", meetings, pairs, today=date(2026, 11, 21))
    assert len(warnings) == 1 and "BI (Indonesia)" in warnings[0]
    assert carry.stale_rate_warnings("2026-11-18", meetings, pairs, today=date(2026, 11, 18)) == []
    old = carry.stale_rate_warnings("2026-11-18", [], pairs, today=date(2027, 1, 15))
    assert len(old) == 1 and "last checked on 18 Nov 2026" in old[0]


def test_real_rates_file_has_checked_dates():
    from modules import usd_outlook
    rates, _ = usd_outlook.load_policy_rates()
    assert "USD" in rates and "USD/BRL" in rates
    date.fromisoformat(usd_outlook.rates_checked())


def test_commodity_moves_use_cache(tmp_path, monkeypatch):
    conn = db.connect(str(tmp_path / "t.db"))
    calls = []

    def fake_fetch(symbols, key):
        calls.append(list(symbols))
        return [{"pair": s, "rate": 10.0, "prev_close": 9.5, "pct_change": 5.26} for s in symbols], []

    monkeypatch.setattr(commodities.fx, "fetch_quotes", fake_fetch)
    rows, warnings = commodities.get_commodity_moves(conn, "2026-11-18", "key")
    assert [r["symbol"] for r in rows] == ["USO", "CPER", "SOYB"] and warnings == []
    commodities.get_commodity_moves(conn, "2026-11-18", "key")  # second time: from the database
    assert calls == [["USO", "CPER", "SOYB"]]
    assert commodities.get_commodity_moves(conn, "2026-11-19", None) == ([], [])


def test_brief_commodity_line():
    names = {"USD/CLP": {"country": "Chile", "currency": "peso"}}
    line = brief.describe_commodity({"name": "Copper", "pct_change": -1.234, "fund": "CPER fund",
                                     "linked": ["USD/CLP"]}, names)
    assert "Copper fell 1.23%" in line and "Chile peso (CLP)" in line


def test_rate_reminders_from_real_files():
    from modules import routine
    assert routine.rate_reminders(date(2026, 11, 18)) == []          # the day the rates were checked
    later = routine.rate_reminders(date(2027, 3, 1))
    assert any("South African Reserve Bank" in m for m in later)     # met on 19 Nov
    assert any("last checked" in m for m in later)
