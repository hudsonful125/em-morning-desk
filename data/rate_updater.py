"""
data/rate_updater.py: keeps data/policy_rates.csv up to date by itself.

Where the numbers come from: the Bank for International Settlements (BIS), the central banks'
own bank, publishes every central bank's policy rate as free daily data, with no API key:
    https://data.bis.org/topics/CBPOL
It uses the same rates this project uses: the Fed's target range MIDPOINT for the US and the
1-year Loan Prime Rate for China. New data comes out about once a week ("around mid-week"),
so a decision usually shows up here 2 to 7 days after the meeting.

What it does each time it runs (daily, before the morning brief and on GitHub):
  1. Downloads the last ~13 months of daily rates for our 11 central banks (one request).
  2. For each country, takes the latest real value and checks it makes sense:
       - it is a number between 0% and 100%,
       - it moved by no more than MAX_JUMP points from the rate we have,
       - it is not OLDER than the rate we already have. If you typed in a newer rate by hand
         (e.g. the day of the meeting), BIS won't overwrite it with last week's number.
  3. If it passes, writes the new rate, the day it changed and today's "checked" date.
     If anything fails (no internet, BIS down, an odd number), that row keeps its last
     known value and you get a warning instead.

Run it by hand from the project folder:   python3 -m data.rate_updater
"""

import csv
import io
import math
import os
import sys
from datetime import date, timedelta

import requests

RATES_PATH = os.path.join("data", "policy_rates.csv")
BIS_URL = "https://stats.bis.org/api/v1/data/WS_CBPOL/D.{codes}/all"
LOOKBACK_DAYS = 400   # BIS sends some countries only now and then, so look back far enough
MAX_JUMP = 10.0       # percentage points; bigger moves are held back for a human to check
SOURCE_NOTE = "BIS central bank policy rates (auto-updated)"

# Country name in policy_rates.csv -> BIS two-letter code
BIS_CODES = {
    "United States": "US", "Brazil": "BR", "Mexico": "MX", "Chile": "CL", "Colombia": "CO",
    "South Africa": "ZA", "Turkey": "TR", "India": "IN", "Indonesia": "ID",
    "South Korea": "KR", "China": "CN",
}
FIELDS = ["country", "pair", "rate", "last_change", "source", "checked"]


# ---------------------------------------------------------------------------
# 1. Download and read the BIS data
# ---------------------------------------------------------------------------

def fetch_bis_csv(codes, today=None, timeout=15):
    """The raw CSV text from BIS for these country codes, or raises on any network/HTTP error."""
    today = today or date.today()
    start = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    url = BIS_URL.format(codes="+".join(codes))
    response = requests.get(url, params={"startPeriod": start, "detail": "dataonly", "format": "csv"},
                            timeout=timeout, headers={"User-Agent": "em-morning-desk"})
    response.raise_for_status()
    return response.text


def parse_bis_csv(text):
    """
    {"BR": [("2026-11-17", 13.75), ...]} sorted by date, real numbers only.
    BIS writes NaN on weekends and holidays; those are skipped.
    """
    series = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            value = float(row["OBS_VALUE"])
            day = date.fromisoformat(row["TIME_PERIOD"]).isoformat()
        except (KeyError, TypeError, ValueError):
            continue
        if math.isnan(value):
            continue
        series.setdefault(row.get("REF_AREA", ""), []).append((day, value))
    return {code: sorted(points) for code, points in series.items()}


def latest_with_start(points):
    """(latest date, latest value, first day of the run at that value), e.g. when a cut took effect."""
    last_day, value = points[-1]
    start = last_day
    for day, v in reversed(points):
        if abs(v - value) > 1e-9:
            break
        start = day
    return last_day, value, start


# ---------------------------------------------------------------------------
# 2. Decide what to change (pure function, easy to test)
# ---------------------------------------------------------------------------

def apply_updates(rows, series, today=None):
    """
    Compare the rows of policy_rates.csv with the BIS series.
    Returns (new_rows, changes, warnings): `changes` are readable lines like
    "Brazil: 13.75% -> 13.50% (from 10 Dec)", `warnings` explain anything held back.
    """
    today = (today or date.today()).isoformat()
    new_rows, changes, warnings = [], [], []
    for row in rows:
        row = dict(row)
        new_rows.append(row)
        country = row["country"]
        code = BIS_CODES.get(country)
        points = series.get(code) if code else None
        if not points:
            warnings.append(f"No BIS data for {country}; kept {row['rate']}%.")
            continue
        as_of, value, started = latest_with_start(points)
        old = float(row["rate"])
        if not 0 <= value <= 100:
            warnings.append(f"BIS gave an odd rate for {country} ({value}); kept {old:g}%.")
            continue
        if abs(value - old) > MAX_JUMP:
            warnings.append(f"BIS shows {country} at {value:g}% vs our {old:g}%, a jump of more than "
                            f"{MAX_JUMP:g} points. Kept {old:g}%; please check it by hand.")
            continue
        if as_of > today:
            continue
        # A rate typed in by hand after BIS's latest data wins (BIS lags a few days).
        if as_of < (row.get("last_change") or ""):
            continue
        if abs(value - old) > 1e-9:
            changes.append(f"{country}: {old:g}% -> {value:g}% (from {date.fromisoformat(started):%d %b})")
            row.update(rate=f"{value:g}", last_change=started, source=SOURCE_NOTE)
        # "checked" = the latest day we know the rate for, so ⏰ reminders clear only once
        # BIS's data covers a meeting.
        if as_of > (row.get("checked") or ""):
            row["checked"] = as_of
    return new_rows, changes, warnings


# ---------------------------------------------------------------------------
# 3. Read, update and save the file
# ---------------------------------------------------------------------------

def read_rows(path=RATES_PATH):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(rows, path=RATES_PATH):
    """Write to a temporary file first, then swap it in, so a crash never leaves half a file."""
    temp = path + ".tmp"
    with open(temp, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, path)


def update_rates_file(path=RATES_PATH, today=None, fetch=fetch_bis_csv):
    """
    The whole job. Returns (changes, warnings). Never raises: on any failure the file is
    left exactly as it was (the last known rates) and the reason is in `warnings`.
    """
    try:
        rows = read_rows(path)
    except (OSError, csv.Error) as error:
        return [], [f"Couldn't read {path}: {error}"]
    codes = sorted({BIS_CODES[r["country"]] for r in rows if r["country"] in BIS_CODES})
    try:
        series = parse_bis_csv(fetch(codes, today))
    except Exception as error:  # noqa: BLE001  (no internet, BIS down, ...: keep the old rates)
        return [], [f"Couldn't get policy rates from BIS ({type(error).__name__}); using the saved rates."]
    if not series:
        return [], ["BIS sent no policy rate data; using the saved rates."]
    new_rows, changes, warnings = apply_updates(rows, series, today)
    if new_rows != rows:
        try:
            write_rows(new_rows, path)
        except OSError as error:
            return [], [f"Couldn't save {path}: {error}"]
    return changes, warnings


if __name__ == "__main__":
    found, problems = update_rates_file()
    for line in found or ["No rate changes."]:
        print(line)
    for line in problems:
        print("Warning:", line, file=sys.stderr)
