"""
modules/routine.py: puts together everything for one morning's brief.

main.py, the website (app.py) and the scheduled job (morning_job.py) all call
make_brief() here, so all three show exactly the same thing.
"""

import os
from datetime import date

import config
import db
from data import bigmac, cb_calendar, commodities, fx, news
from modules import archive, brief, carry, prices, usd_outlook


def todays_meetings(today=None):
    """Central bank rate decisions in the next 14 days, as readable lines."""
    today = today or date.today()
    meetings = cb_calendar.upcoming(cb_calendar.load_meetings(), today)
    return [cb_calendar.describe(m, today) for m in meetings]


def rate_reminders(today=None):
    """Warnings that data/policy_rates.csv may be out of date (see carry.stale_rate_warnings)."""
    try:
        rates, _ = usd_outlook.load_policy_rates()
        checked = usd_outlook.rates_checked_by_country()
    except (OSError, KeyError, ValueError):
        return ["Couldn't read data/policy_rates.csv."]
    if not checked:
        return ["data/policy_rates.csv has no rates in it."]
    country_to_pair = {c["country"]: c["pair"] for c in config.CURRENCIES if c["pair"] in rates}
    return carry.stale_rate_warnings(checked, cb_calendar.load_meetings(), country_to_pair,
                                     today or date.today())


def price_lines(fx_rows):
    """One "connect it to the news" sentence per item in config.ITEMS."""
    lines = []
    for item in config.ITEMS:
        local_prices, _, _ = bigmac.get_item_prices(item)
        table = prices.build_price_table(fx_rows, local_prices)
        if table:
            lines.append(prices.news_tie_in(table, item["name"], item.get("phrase")))
    return lines


def make_brief(conn, today=None, refresh=False):
    """
    Get today's numbers and headlines, then today's brief (saved copy, or a new one from Claude).
    Returns a dict: fx_rows, headlines, summary, meetings, commodities, text, error, warnings.
    `text` is None if there was no FX data or Claude couldn't write the brief (see `error`).
    Also saves briefs/<today>.md whenever there is a brief.
    """
    today = today or date.today()
    day = today.isoformat()
    result = {"fx_rows": [], "headlines": [], "summary": None, "meetings": [], "commodities": [],
              "text": None, "error": None, "warnings": []}

    # 1. Numbers (Python)
    fx_rows, warnings = fx.get_fx_rates(conn, day, os.getenv("TWELVE_DATA_KEY"), refresh=refresh)
    result["warnings"] += warnings
    if not fx_rows:
        result["error"] = ("No FX data available, so there's no brief today. "
                           "Check your Twelve Data key and internet connection.")
        return result

    # 2. Headlines, upcoming central bank meetings, and the summary (Python)
    headlines, warnings = news.get_news(conn, day, os.getenv("FINNHUB_KEY"), refresh=refresh)
    result["warnings"] += warnings
    summary = brief.build_summary(fx_rows, headlines)
    meetings = todays_meetings(today)
    commodity_moves, warnings = commodities.get_commodity_moves(
        conn, day, os.getenv("TWELVE_DATA_KEY"), refresh=refresh)
    result["warnings"] += warnings
    result.update(fx_rows=fx_rows, headlines=headlines, summary=summary, meetings=meetings,
                  commodities=commodity_moves)

    # 3. Words (Claude): today's saved copy unless refresh
    text = None if refresh else db.load_brief(conn, day)
    if text is None:
        fact_sheet = brief.summary_to_text(summary, headlines, meetings, commodity_moves)
        text, error = brief.write_brief(fact_sheet, os.getenv("ANTHROPIC_API_KEY"))
        if error:
            result["error"] = error
            return result
        db.save_brief(conn, day, text)
    result["text"] = text

    # 4. Keep a copy: briefs/YYYY-MM-DD.md
    try:
        archive.save_brief_file(day, summary, headlines, text,
                                meetings=meetings, price_lines=price_lines(fx_rows))
    except OSError as error:
        result["warnings"].append(f"Couldn't save the brief file: {error}")
    return result
