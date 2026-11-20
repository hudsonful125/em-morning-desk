"""Tests for data/rate_updater.py: the automatic policy rate updates from BIS (no internet needed)."""

import os
import shutil
from datetime import date

import pytest

from data import rate_updater
from modules import carry

FIXTURE = os.path.join("tests", "fixtures", "bis_cbpol_sample.csv")
HEADER = "country,pair,rate,last_change,source,checked\n"


def sample():
    with open(FIXTURE, encoding="utf-8") as f:
        return f.read()


def write_rates(path, lines):
    path.write_text(HEADER + "".join(line + "\n" for line in lines), encoding="utf-8")


def test_parse_skips_nan_and_sorts():
    series = rate_updater.parse_bis_csv(sample())
    assert series["CL"] == [("2026-11-02", 4.5), ("2026-11-03", 4.5)]
    assert [d for d, _ in series["BR"]] == ["2026-12-09", "2026-12-10", "2026-12-11"]
    assert series["US"] == [("2026-12-11", 3.875)]


def test_latest_with_start_finds_the_day_of_the_cut():
    points = [("2026-12-09", 13.75), ("2026-12-10", 13.5), ("2026-12-11", 13.5)]
    assert rate_updater.latest_with_start(points) == ("2026-12-11", 13.5, "2026-12-10")


def test_update_changes_rate_and_keeps_safe_rows(tmp_path):
    path = tmp_path / "rates.csv"
    write_rates(path, [
        "United States,,3.875,2026-09,cbrates.com,2026-11-19",
        "Brazil,USD/BRL,13.75,2026-09-17,cbrates.com,2026-11-19",
        "Indonesia,USD/IDR,6.00,2026-11-18,Bank Indonesia,2026-11-19",   # typed in after BIS's data
        "Turkey,USD/TRY,36.00,2026-10-22,cbrates.com,2026-11-19",        # BIS says 99: too big a jump
        "India,USD/INR,5.50,2026-10-07,cbrates.com,2026-11-19",          # not in the BIS sample
    ])
    changes, warnings = rate_updater.update_rates_file(str(path), date(2026, 12, 14),
                                                       fetch=lambda codes, today: sample())
    rows = {r["country"]: r for r in rate_updater.read_rows(str(path))}
    assert changes == ["Brazil: 13.75% -> 13.5% (from 10 Dec)"]
    assert rows["Brazil"]["rate"] == "13.5" and rows["Brazil"]["last_change"] == "2026-12-10"
    assert rows["Brazil"]["checked"] == "2026-12-11" and "BIS" in rows["Brazil"]["source"]
    assert rows["United States"]["rate"] == "3.875" and rows["United States"]["checked"] == "2026-12-11"
    assert rows["Indonesia"]["rate"] == "6.00" and rows["Indonesia"]["checked"] == "2026-11-19"
    assert rows["Turkey"]["rate"] == "36.00"
    assert any("Turkey" in w and "check it by hand" in w for w in warnings)
    assert any("India" in w for w in warnings)


def test_no_internet_keeps_the_file(tmp_path):
    path = tmp_path / "rates.csv"
    write_rates(path, ["Brazil,USD/BRL,13.75,2026-09-17,cbrates.com,2026-11-19"])
    before = path.read_text(encoding="utf-8")

    def broken(codes, today):
        raise ConnectionError("offline")

    changes, warnings = rate_updater.update_rates_file(str(path), date(2026, 12, 14), fetch=broken)
    assert changes == [] and "using the saved rates" in warnings[0]
    assert path.read_text(encoding="utf-8") == before
    changes, warnings = rate_updater.update_rates_file(str(path), fetch=lambda c, t: "FREQ,REF_AREA\n")
    assert changes == [] and path.read_text(encoding="utf-8") == before


def test_real_rates_file_countries_all_have_bis_codes():
    rows = rate_updater.read_rows()
    assert {r["country"] for r in rows} <= set(rate_updater.BIS_CODES)


def test_real_file_round_trips_unchanged(tmp_path):
    path = tmp_path / "rates.csv"
    shutil.copy(rate_updater.RATES_PATH, path)
    rows = rate_updater.read_rows(str(path))
    rate_updater.write_rows(rows, str(path))
    assert rate_updater.read_rows(str(path)) == rows


def test_reminders_clear_per_country():
    meetings = [{"date": "2026-12-09", "country": "Brazil", "bank": "Copom"},
                {"date": "2026-12-10", "country": "Turkey", "bank": "CBRT"}]
    pairs = {"Brazil": "USD/BRL", "Turkey": "USD/TRY"}
    checked = {"Brazil": "2026-12-11", "Turkey": "2026-12-01"}
    warnings = carry.stale_rate_warnings(checked, meetings, pairs, today=date(2026, 12, 14))
    assert len(warnings) == 1 and "CBRT (Turkey)" in warnings[0]
