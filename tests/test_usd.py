"""Tests for the USD vs EM history, scenarios and the dollar-in-trade map data."""

import json
import math

import pytest

from data import fx_history
from modules import usd_outlook, usd_trade


def monthly(start_value, growth_per_month, months=72):
    """Fake month-end closes: [('2020-12-01', v), ...] growing by a fixed % each month."""
    points, value = [], start_value
    for i in range(months + 1):
        year, month = 2020 + (11 + i) // 12, (11 + i) % 12 + 1
        points.append((f"{year}-{month:02d}-01", value))
        value *= 1 + growth_per_month
    return points


def test_changes_and_cagr():
    history = {"USD/BRL": monthly(5.0, 0.01)}
    row = usd_outlook.changes(history)[0]
    assert row["1 month"] == pytest.approx(1.0)
    assert row["1 year"] == pytest.approx((1.01 ** 12 - 1) * 100)
    assert row["cagr_5y"] == pytest.approx((1.01 ** 12 - 1) * 100)
    assert usd_outlook.changes({"USD/MXN": [("2026-11-01", 18.0)]})[0]["5 years"] is None


def test_basket_and_rebased():
    rows = [{"1 year": 10.0}, {"1 year": -4.0}, {"1 year": None}]
    assert usd_outlook.basket_average(rows, "1 year") == 3.0
    series = usd_outlook.rebased(monthly(2.0, 0.02), months=12)
    assert len(series) == 13 and series[0][1] == 100


def test_scenarios():
    paths = usd_outlook.scenarios(5.0, cagr_pct=10, local_rate=13.75, us_rate=3.875, ppp_rate=3.0)
    assert paths["Trend"][1] == pytest.approx(5.5)
    assert paths["Rate gap"][1] == pytest.approx(5.0 * 1.1375 / 1.03875)
    # Fair value: half of the (log) gap closes in 5 years
    assert paths["Fair value"][5] == pytest.approx(math.sqrt(5.0 * 3.0))
    assert set(usd_outlook.scenarios(5.0)) == set()
    assert usd_outlook.dollar_move(5.0, 5.5) == pytest.approx(10.0)


def test_policy_rates_file():
    rates, dates = usd_outlook.load_policy_rates()
    assert rates["USD"] > 0 and rates["USD/BRL"] > rates["USD"]
    assert len(rates) == 11 and all(dates.values())


def test_fetch_history_batches_and_retries(monkeypatch):
    calls, sleeps = [], []

    class Reply:
        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    def fake_get(url, params, timeout):
        calls.append(params["symbol"])
        if len(calls) == 1:
            return Reply({"code": 429, "status": "error", "message": "limit"})
        pairs = params["symbol"].split(",")
        one = {"values": [{"datetime": "2026-11-01", "close": "2.0"}, {"datetime": "2026-10-01", "close": "1.0"}]}
        return Reply(one if len(pairs) == 1 else {p: one for p in pairs})

    monkeypatch.setattr(fx_history.requests, "get", fake_get)
    pairs = [f"USD/X{i}" for i in range(10)]
    history, errors = fx_history.fetch_history(pairs, "key", sleep=sleeps.append)
    assert not errors and len(history) == 10
    assert history["USD/X0"] == [("2026-10-01", 1.0), ("2026-11-01", 2.0)]
    assert len(calls) == 3 and sleeps == [61, 61]  # one retry after the limit, one between batches


def test_history_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cache").mkdir()
    full = {s: [["2026-11-01", 5.5]] for s in fx_history.wanted_symbols()}
    (tmp_path / "cache" / "fx_history.json").write_text(json.dumps(full))
    history, warnings = fx_history.get_history(None)
    assert history["USD/BRL"] == [("2026-11-01", 5.5)] and warnings == []
    # An older cache without the commodity funds counts as out of date
    (tmp_path / "cache" / "fx_history.json").write_text(json.dumps({"USD/BRL": [["2026-11-01", 5.5]]}))
    history, warnings = fx_history.get_history(None)
    assert "USD/BRL" in history and "No TWELVE_DATA_KEY" in warnings[0]


def test_trade_scenarios(tmp_path):
    path = tmp_path / "inv.csv"
    lines = ["country,iso3,iso_num,year,usd_export_share,usd_import_share"]
    lines += [f"Brazil,BRA,76,{y},{90 - (y - 2014)},{80}" for y in range(2014, 2024)]
    lines += ["Chile,CHL,152,2022,85,"]
    path.write_text("\n".join(lines))
    rows = usd_trade.load(path)
    latest = usd_trade.latest_by_country(rows, "usd_export_share")
    assert [(r["country"], r["year"]) for r in latest] == [("Brazil", 2023), ("Chile", 2022)]
    assert [r["country"] for r in usd_trade.latest_by_country(rows, "usd_import_share")] == ["Brazil"]
    paths = usd_trade.scenarios(usd_trade.history(rows, "BRA", "usd_export_share"), [2028, 2033])
    assert paths["Steady"][2028] == 81 and paths["Trend"][2028] == pytest.approx(76)
    assert set(usd_trade.scenarios([(2022, 85.0)], [2027])) == {"Steady"}
    assert usd_trade.load(tmp_path / "missing.csv") == []
