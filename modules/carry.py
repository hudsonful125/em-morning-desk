"""
modules/carry.py: the carry trade table, commodity links, and the "are our rates stale?" check.

CARRY TRADE, in one paragraph: borrow in dollars at the US rate, hold the EM currency and earn
its (higher) local rate. You pocket the gap ("carry") as long as the currency doesn't fall by
more than that. Volatility tells you how big those falls tend to be, so desks compare the two:
carry divided by volatility ("carry-to-vol") is a rough reward-for-risk score.

All the math is here in Python; the website only draws it.
"""

import math
from datetime import date, timedelta

VOL_MONTHS = 36           # volatility from the last 3 years of monthly moves
CORRELATION_MONTHS = 60   # commodity links from the last 5 years
STALE_AFTER_DAYS = 45     # nag if nobody has checked the rates file for this long


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def monthly_returns(points, months):
    """% changes between consecutive monthly closes, the last `months` of them."""
    window = points[-(months + 1):]
    return [(window[i][1] / window[i - 1][1] - 1) * 100 for i in range(1, len(window))]


def stdev(values):
    """Sample standard deviation (None if fewer than 2 values)."""
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def correlation(xs, ys):
    """Pearson correlation of two equal-length lists (None if it can't be worked out)."""
    n = min(len(xs), len(ys))
    xs, ys = xs[-n:], ys[-n:]
    sx, sy = stdev(xs), stdev(ys)
    if n < 3 or not sx or not sy:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / ((n - 1) * sx * sy)


# ---------------------------------------------------------------------------
# Carry trade table
# ---------------------------------------------------------------------------

def annual_vol(points, months=VOL_MONTHS):
    """Annualised volatility (%) of the exchange rate from monthly moves: monthly stdev x sqrt(12)."""
    sd = stdev(monthly_returns(points, months))
    return sd * math.sqrt(12) if sd is not None else None


def carry_table(rates, history, one_year_moves):
    """
    One row per currency, highest carry first:
      carry         = local policy rate - US policy rate (% a year)
      vol           = annualised volatility of USD/XXX (%)
      carry_to_vol  = carry / vol
      past_year     = rough result of the trade over the last year: carry minus the dollar's
                      % gain vs the currency (uses today's rates, so it's an approximation)
    `rates` from usd_outlook.load_policy_rates(); `one_year_moves` = {pair: dollar's 1-year % change}.
    """
    us = rates["USD"]
    rows = []
    for pair, points in history.items():
        if pair not in rates:
            continue
        carry = rates[pair] - us
        vol = annual_vol(points)
        move = one_year_moves.get(pair)
        rows.append({
            "pair": pair, "local_rate": rates[pair], "carry": carry, "vol": vol,
            "carry_to_vol": carry / vol if vol else None,
            "past_year": carry - move if move is not None else None,
        })
    return sorted(rows, key=lambda r: r["carry"], reverse=True)


# ---------------------------------------------------------------------------
# Commodity links
# ---------------------------------------------------------------------------

def commodity_links(history, currency_pairs, commodity_symbols, months=CORRELATION_MONTHS):
    """
    Correlation between each commodity's monthly % change and each currency's monthly % change
    in value against the dollar (so +1 = the currency rises when the commodity rises).
    Returns {(pair, symbol): correlation or None}.
    """
    out = {}
    for symbol in commodity_symbols:
        if symbol not in history:
            continue
        commodity = monthly_returns(history[symbol], months)
        for pair in currency_pairs:
            if pair not in history:
                continue
            # USD/XXX up = currency down, so flip the sign to get the currency's own move
            currency = [-r for r in monthly_returns(history[pair], months)]
            out[(pair, symbol)] = correlation(currency, commodity)
    return out


# ---------------------------------------------------------------------------
# Are the policy rates stale?
# ---------------------------------------------------------------------------

def stale_rate_warnings(checked, meetings, country_to_pair, today=None):
    """
    Warnings for each central bank that has met since its rate was last checked
    (including a meeting on the day of the check, whose result may not have been in yet),
    plus one if the file hasn't been checked for STALE_AFTER_DAYS.
    `checked` = 'YYYY-MM-DD' for the whole file, or {country: 'YYYY-MM-DD'} for each bank
    (data/rate_updater.py moves each bank's date forward as new BIS data comes in).
    `meetings` = rows from data/central_bank_calendar.csv.
    """
    today = today or date.today()
    if isinstance(checked, dict):
        by_country = {c: date.fromisoformat(d) for c, d in checked.items()}
        oldest = min(by_country.values())
    else:
        oldest = date.fromisoformat(checked)
        by_country = {}
    warnings = []
    for m in meetings:
        day = date.fromisoformat(m["date"])
        checked_day = by_country.get(m["country"], oldest)
        if checked_day <= day < today and m["country"] in country_to_pair:
            warnings.append(f"{m['bank']} ({m['country']}) met on {day:%a %d %b}. The automatic update "
                            f"usually picks up the new rate within a week; until then you can type it "
                            f"into data/policy_rates.csv.")
    if today - oldest > timedelta(days=STALE_AFTER_DAYS):
        warnings.append(f"The interest rates in data/policy_rates.csv were last checked on "
                        f"{oldest:%d %b %Y}. Please check them again.")
    return warnings
