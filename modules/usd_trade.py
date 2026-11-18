"""
modules/usd_trade.py: how much of each country's trade is invoiced (priced) in US dollars.

The data come from the invoicing-currency dataset of Boz, Casas, Georgiadis, Gopinath,
Le Mezo, Mehl and Nguyen (2022), "Patterns of invoicing currency in global trade: New evidence",
Journal of International Economics 136 (replication data on Mendeley Data, doi 10.17632/6z6w78968m.1,
CC BY 4.0, file all_countries_update.dta). 110 countries, 1989-2019. Saved as
data/usd_invoicing.csv with one row per country per year:

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
