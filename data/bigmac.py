"""
data/bigmac.py: local prices for the "Prices Around the World" section.

Two places prices can come from:
  1. The Economist's Big Mac data (free, MIT license), downloaded from GitHub.
     They update it twice a year (January and July). We save a copy in cache/
     and only download again when that copy is more than 30 days old.
  2. Your own small CSV for any other item (iPhone, Netflix, gas...). See
     items/_template.csv and the ITEMS list in config.py.

Both give back the same thing: a dict of {currency code: local price},
e.g. {"USD": 6.22, "BRL": 23.9, ...}, plus the date the prices are from.
"""

import csv
import os
import time

import requests

import config

BIG_MAC_URL = ("https://raw.githubusercontent.com/TheEconomist/big-mac-data/"
               "master/source-data/big-mac-source-data-v2.csv")
CACHE_PATH = os.path.join("cache", "big-mac-source-data.csv")


# ---------------------------------------------------------------------------
# Reading price CSVs (pure Python, easy to test)
# ---------------------------------------------------------------------------

def latest_prices(rows):
    """
    From rows of {currency_code, local_price, date}, keep the most recent price
    for each currency. Returns (prices_dict, newest_date).
    Rows with a missing or zero price are skipped.
    """
    prices, dates = {}, {}
    for row in rows:
        code = (row.get("currency_code") or "").strip().upper()
        date = (row.get("date") or "").strip()
        try:
            price = float(row.get("local_price") or 0)
        except ValueError:
            continue
        if not code or price <= 0:
            continue
        # Dates are written YYYY-MM-DD, so comparing them as text works
        if code not in dates or date > dates[code]:
            prices[code] = price
            dates[code] = date
    newest = max(dates.values()) if dates else ""
    return prices, newest


def read_price_csv(path):
    """Read a price CSV (columns: currency_code, local_price, date) into (prices, date)."""
    with open(path, newline="", encoding="utf-8") as f:
        return latest_prices(csv.DictReader(f))


# ---------------------------------------------------------------------------
# The Economist download, with a 30-day cache
# ---------------------------------------------------------------------------

def cache_age_days(path):
    """How many days old a file is, or None if it doesn't exist."""
    if not os.path.exists(path):
        return None
    return (time.time() - os.path.getmtime(path)) / 86400


def ensure_big_mac_csv(max_age_days=None):
    """
    Make sure we have a recent copy of The Economist's CSV.
    Returns (path or None, warnings).
    """
    max_age_days = max_age_days or config.BIG_MAC_CACHE_DAYS
    warnings = []
    age = cache_age_days(CACHE_PATH)
    if age is not None and age < max_age_days:
        return CACHE_PATH, warnings  # fresh enough: no download needed

    try:
        response = requests.get(BIG_MAC_URL, timeout=30)
        response.raise_for_status()
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            f.write(response.text)
        return CACHE_PATH, warnings
    except (requests.RequestException, OSError) as error:
        if age is not None:
            warnings.append(f"Couldn't refresh the Big Mac data ({error}); using the saved copy.")
            return CACHE_PATH, warnings
        warnings.append(f"Couldn't download the Big Mac data from GitHub: {error}")
        return None, warnings


def get_item_prices(item):
    """
    Get local prices for one item from config.ITEMS.
    Returns (prices_dict, date, warnings).
    """
    if item["source"] == "economist":
        path, warnings = ensure_big_mac_csv()
        if not path:
            return {}, "", warnings
    else:
        path, warnings = item["source"], []
        if not os.path.exists(path):
            return {}, "", [f"Price file not found for {item['name']}: {path}"]

    prices, date = read_price_csv(path)
    if "USD" not in prices:
        warnings.append(f"{item['name']}: no US (USD) price found, so it can't be compared.")
    return prices, date, warnings
