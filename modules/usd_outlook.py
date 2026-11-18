"""
modules/usd_outlook.py: the math for "USD vs emerging markets" and the long-term USD scenarios.

All numbers are worked out here in Python. Pairs are quoted USD/XXX, so a RISE means the
dollar got STRONGER (1 dollar buys more local currency).

The scenarios are not forecasts. Each one answers "what if...?" with a simple, stated rule:
  - Trend:         the last 5 years' average yearly move keeps going.
  - Rate gap:      the exchange rate moves by the interest-rate difference each year. This is
                   how forward rates are priced (covered interest parity): a currency with a
                   higher interest rate is priced to weaken against the dollar by about the gap.
  - Fair value:    the rate drifts toward the Big Mac "fair" (PPP) rate, closing half the gap
                   every 5 years. Studies find PPP gaps shrink slowly, roughly that pace.
"""

import csv
import math
import os

RATES_PATH = os.path.join("data", "policy_rates.csv")
HORIZONS = [1, 3, 5]  # years ahead
PERIODS = {"1 month": 1, "1 year": 12, "5 years": 60}
FAIR_VALUE_HALF_LIFE = 5  # years for half of the gap to the PPP rate to close


# ---------------------------------------------------------------------------
# Looking back: how has the dollar done against each currency?
# ---------------------------------------------------------------------------

def value_months_ago(points, months):
    """The close `months` months before the latest one, or None if the history is too short."""
    if len(points) <= months:
        return None
    return points[-1 - months][1]


def pct(new, old):
    return (new / old - 1) * 100


def changes(history):
    """
    For each pair: latest rate and the dollar's % change over 1 month, 1 year and 5 years.
    Returns a list of dicts like {"pair", "latest", "1 month", "1 year", "5 years", "cagr_5y"}.
    """
    rows = []
    for pair, points in history.items():
        if not points:
            continue
        latest = points[-1][1]
        row = {"pair": pair, "latest": latest, "as_of": points[-1][0]}
        for label, months in PERIODS.items():
            old = value_months_ago(points, months)
            row[label] = pct(latest, old) if old else None
        old_5y = value_months_ago(points, 60)
        row["cagr_5y"] = ((latest / old_5y) ** (1 / 5) - 1) * 100 if old_5y else None
        rows.append(row)
    return rows


def basket_average(rows, label):
    """Equal-weighted average move of the dollar against all the currencies (None if no data)."""
    values = [r[label] for r in rows if r.get(label) is not None]
    return sum(values) / len(values) if values else None


def rebased(points, months=60):
    """The last `months` months scaled so the first value is 100 (for a comparison chart)."""
    window = points[-(months + 1):]
    if not window:
        return []
    base = window[0][1]
    return [(day, value / base * 100) for day, value in window]


# ---------------------------------------------------------------------------
# Looking ahead: scenarios
# ---------------------------------------------------------------------------

def load_policy_rates(path=RATES_PATH):
    """{"USD": 3.875, "USD/BRL": 13.75, ...} plus {pair: last_change} from data/policy_rates.csv."""
    rates, dates = {}, {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = row["pair"] or "USD"
            rates[key] = float(row["rate"])
            dates[key] = row["last_change"]
    return rates, dates


def rates_checked(path=RATES_PATH):
    """The oldest 'checked' date in data/policy_rates.csv (when someone last confirmed the rates)."""
    with open(path, newline="", encoding="utf-8") as f:
        return min(row["checked"] for row in csv.DictReader(f))


def trend_path(spot, cagr_pct, years):
    return spot * (1 + cagr_pct / 100) ** years


def rate_gap_path(spot, local_rate_pct, us_rate_pct, years):
    """Forward-style rate: spot x ((1 + local rate) / (1 + US rate)) ^ years."""
    return spot * ((1 + local_rate_pct / 100) / (1 + us_rate_pct / 100)) ** years


def fair_value_path(spot, ppp_rate, years, half_life=FAIR_VALUE_HALF_LIFE):
    """Move toward the PPP rate, closing half of the (log) gap every `half_life` years."""
    share_closed = 1 - 0.5 ** (years / half_life)
    return math.exp(math.log(spot) + share_closed * (math.log(ppp_rate) - math.log(spot)))


def scenarios(spot, cagr_pct=None, local_rate=None, us_rate=None, ppp_rate=None, horizons=HORIZONS):
    """
    Projected USD/XXX rates for each scenario we have the inputs for.
    Returns {"Trend": {1: rate, 3: rate, 5: rate}, "Rate gap": {...}, "Fair value": {...}}.
    """
    out = {}
    if cagr_pct is not None:
        out["Trend"] = {y: trend_path(spot, cagr_pct, y) for y in horizons}
    if local_rate is not None and us_rate is not None:
        out["Rate gap"] = {y: rate_gap_path(spot, local_rate, us_rate, y) for y in horizons}
    if ppp_rate:
        out["Fair value"] = {y: fair_value_path(spot, ppp_rate, y) for y in horizons}
    return out


def dollar_move(spot, future):
    """% change in USD/XXX: positive = the dollar is stronger in that scenario."""
    return pct(future, spot)
