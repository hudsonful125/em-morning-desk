"""
modules/usd_trade.py: how much of each country's trade is invoiced (priced) in US dollars.

The data come from the Global Trade Invoicing Currency Patterns Database (version of
29 August 2025) by Boz, Brüggen, Casas, Georgiadis, Gopinath and Mehl (2025), "Patterns of
Invoicing Currency in Global Trade in a Fragmenting World Economy", IMF Working Paper 25/178.
Downloaded from globalcurrenciesdatabase.com (licence: CC BY-NC-SA 4.0, so this CSV is shared
under the same licence and must not be used commercially). It extends the 2022 dataset to 2023
(a few countries to 2024): 130 countries. Saved as data/usd_invoicing.csv, one row per country per year:

    country, iso3, iso_num, year, usd_export_share, usd_import_share

iso_num is the 3-digit UN country code, which the world map uses to colour each country.

The "projections" are two simple, labelled scenarios, not forecasts:
  - Steady: the share stays where it was in the latest year.
  - Trend:  the straight-line trend of the last 10 years keeps going (kept between 0% and 100%).
"""

import csv
import os

PATH = os.path.join("data", "usd_invoicing.csv")
TREND_YEARS = 10

# ISO codes of the desk's countries (config.CURRENCIES), to find them in the dataset.
ISO3 = {"Brazil": "BRA", "Mexico": "MEX", "India": "IND", "South Africa": "ZAF", "Turkey": "TUR",
        "China": "CHN", "South Korea": "KOR", "Indonesia": "IDN", "Chile": "CHL", "Colombia": "COL"}

# Why some of the desk's countries have no numbers.
NO_DATA = {
    "MEX": "Not measured: Mexican customs forms don't have to record the invoicing currency.",
    "CHN": "Not measured: China doesn't publish invoicing currencies. Its official payment data "
           "(SAFE) show the dollar's share of cross-border settlement falling from about 90% to "
           "about 50% by 2023 as the renminbi took over (payments, not invoicing).",
}


def load(path=PATH):
    """All rows from the CSV as dicts with numbers converted, or [] if the file isn't there yet."""
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out = {"country": row["country"], "iso3": row["iso3"],
                   "iso_num": int(row["iso_num"]), "year": int(row["year"])}
            for key in ("usd_export_share", "usd_import_share"):
                value = (row.get(key) or "").strip()
                out[key] = float(value) if value else None
            rows.append(out)
    return rows


def latest_by_country(rows, column):
    """The most recent non-empty value of `column` for each country -> list of rows."""
    best = {}
    for row in rows:
        if row[column] is None:
            continue
        if row["iso3"] not in best or row["year"] > best[row["iso3"]]["year"]:
            best[row["iso3"]] = row
    return sorted(best.values(), key=lambda r: r["country"])


def history(rows, iso3, column):
    """[(year, share), ...] for one country, oldest first."""
    return sorted((r["year"], r[column]) for r in rows if r["iso3"] == iso3 and r[column] is not None)


def linear_trend(points):
    """Least-squares straight line through (year, value) points -> (slope per year, intercept)."""
    n = len(points)
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    spread = sum((x - mean_x) ** 2 for x, _ in points)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / spread if spread else 0.0
    return slope, mean_y - slope * mean_x


def scenarios(points, target_years):
    """
    {"Steady": {year: share}, "Trend": {year: share}} for each target year.
    Trend needs at least 3 years of data in the last TREND_YEARS years; otherwise only Steady.
    """
    if not points:
        return {}
    last_year, last_value = points[-1]
    out = {"Steady": {y: last_value for y in target_years}}
    recent = [p for p in points if p[0] > last_year - TREND_YEARS]
    if len(recent) >= 3:
        slope, intercept = linear_trend(recent)
        out["Trend"] = {y: min(100.0, max(0.0, slope * y + intercept)) for y in target_years}
    return out


def desk_countries(rows, countries):
    """
    One row per desk country: latest USD share of exports and imports (with years), or a note
    saying why there's no data. `countries` = names from config.CURRENCIES.
    """
    out = []
    for name in countries:
        iso3 = ISO3.get(name)
        row = {"country": name}
        for column, label in (("usd_export_share", "exports"), ("usd_import_share", "imports")):
            points = history(rows, iso3, column)
            row[label] = points[-1] if points else None
        row["note"] = NO_DATA.get(iso3, "" if row["exports"] or row["imports"] else "No data.")
        out.append(row)
    return out


MAX_GAP = 3            # use a reading up to 3 years old when a country skipped the chosen year
PROJECT_FROM = 2015    # only project countries whose latest data is from 2015 or later


def map_for_year(rows, column, year):
    """
    Each country's USD share for one year of the map slider -> list of
    {iso_num, country, share, data_year, kind}, where kind is "Actual" or "Projected".
      - Up to a country's latest data: its reading for that year (or the closest earlier one,
        at most MAX_GAP years before).
      - After its latest data: the Trend scenario (or Steady if there's too little data),
        only for countries with data from PROJECT_FROM or later.
    """
    by_country = {}
    for r in rows:
        if r[column] is not None:
            by_country.setdefault(r["iso3"], []).append(r)
    out = []
    for iso3, country_rows in by_country.items():
        points = sorted((r["year"], r[column]) for r in country_rows)
        info = {"iso_num": country_rows[0]["iso_num"], "country": country_rows[0]["country"]}
        last_year = points[-1][0]
        if year <= last_year or (last_year < PROJECT_FROM and year - last_year <= MAX_GAP):
            earlier = [p for p in points if year - MAX_GAP <= p[0] <= year]
            if earlier:
                out.append(dict(info, share=earlier[-1][1], data_year=earlier[-1][0], kind="Actual"))
        elif last_year >= PROJECT_FROM:
            paths = scenarios(points, [year])
            path = paths.get("Trend") or paths["Steady"]
            out.append(dict(info, share=path[year], data_year=last_year, kind="Projected"))
    return sorted(out, key=lambda r: r["country"])
