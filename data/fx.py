"""
data/fx.py: gets today's EM exchange rates from Twelve Data.

For each pair we need two numbers:
  - rate:        the latest price (e.g. USD/BRL = 5.6478)
  - prev_close:  yesterday's closing price (e.g. 5.5615)
and then Python works out the % change. (The LLM never does math in this project.)

Twelve Data's /quote endpoint gives both numbers in one request, and it accepts
several symbols at once separated by commas, which saves API calls.

Results are cached in SQLite: if you run the app twice on the same day,
the second run reads from the database and spends no API credits.
"""

import time

import requests

import config
import db

QUOTE_URL = "https://api.twelvedata.com/quote"


# ---------------------------------------------------------------------------
# Math (pure Python, easy to test)
# ---------------------------------------------------------------------------

def pct_change(new, old):
    """
    Percentage change from `old` to `new`.
    Example: pct_change(5.40, 5.00) -> 8.0   (an 8% rise)
    """
    return (new - old) / old * 100


def direction_word(pct):
    """
    Plain-English read of a USD/XXX move, from the local currency's point of view.
    USD/XXX going UP means 1 dollar buys MORE local currency, so the local currency WEAKENED.
    """
    if pct > 0:
        return "weaker"
    if pct < 0:
        return "stronger"
    return "flat"


def sort_by_biggest_move(rows):
    """Sort rows so the biggest move (up or down) comes first."""
    return sorted(rows, key=lambda row: abs(row["pct_change"]), reverse=True)


# ---------------------------------------------------------------------------
# Talking to the Twelve Data API
# ---------------------------------------------------------------------------

def chunk(items, size):
    """Split a list into smaller lists of at most `size` items. [1,2,3,4,5], 2 -> [[1,2],[3,4],[5]]"""
    return [items[i:i + size] for i in range(0, len(items), size)]


def parse_quotes(data, pairs):
    """
    Turn Twelve Data's JSON reply into our simple rows.

    Twelve Data replies in two shapes:
      - one symbol:      {"symbol": "USD/BRL", "close": "5.64", ...}
      - several symbols: {"USD/BRL": {...}, "USD/MXN": {...}}
    A symbol that failed comes back as {"status": "error", "message": "..."}.

    Returns (rows, errors): rows is a list of dicts, errors is a list of messages.
    """
    # Make the one-symbol shape look like the several-symbols shape.
    if len(pairs) == 1:
        data = {pairs[0]: data}

    rows, errors = [], []
    for pair in pairs:
        quote = data.get(pair)
        if not quote or quote.get("status") == "error":
            message = (quote or {}).get("message", "no data returned")
            errors.append(f"{pair}: {message}")
            continue
        try:
            rate = float(quote["close"])
            prev_close = float(quote["previous_close"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{pair}: reply was missing the close or previous close")
            continue
        rows.append({
            "pair": pair,
            "rate": rate,
            "prev_close": prev_close,
            "pct_change": pct_change(rate, prev_close),
        })
    return rows, errors


def fetch_quotes(pairs, api_key):
    """
    Ask Twelve Data for quotes on a list of pairs, respecting the free plan's
    limit of 8 credits per minute. Returns (rows, errors).
    """
    all_rows, all_errors = [], []
    batches = chunk(pairs, config.TWELVE_DATA_MAX_PER_MINUTE)

    for i, batch in enumerate(batches):
        if i > 0:
            # Wait a minute so we don't go over the free plan's rate limit.
            print(f"Waiting 60 seconds for the Twelve Data rate limit "
                  f"({len(batch)} more pairs to fetch)...")
            time.sleep(61)

        try:
            response = requests.get(
                QUOTE_URL,
                params={"symbol": ",".join(batch), "apikey": api_key},
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as error:
            all_errors.append(f"Could not reach Twelve Data for {', '.join(batch)}: {error}")
            continue

        # A whole-request failure (bad key, out of credits) has "status": "error" at the top level.
        if data.get("status") == "error" and "symbol" not in data:
            all_errors.append(f"Twelve Data error: {data.get('message', 'unknown error')}")
            continue

        rows, errors = parse_quotes(data, batch)
        all_rows.extend(rows)
        all_errors.extend(errors)

    return all_rows, all_errors


# ---------------------------------------------------------------------------
# The one function the rest of the app calls
# ---------------------------------------------------------------------------

def get_fx_rates(conn, date, api_key, refresh=False):
    """
    Return today's FX rows, sorted by biggest mover, plus a list of warning messages.

    1. Look in the database for rows already saved today (free, no API call).
    2. Fetch only the pairs that are missing (or all of them if refresh=True).
    3. Save the new rows, then return everything.
    """
    warnings = []
    wanted = [c["pair"] for c in config.CURRENCIES]

    cached = [] if refresh else db.load_fx_rates(conn, date)
    cached_pairs = {row["pair"] for row in cached}
    missing = [pair for pair in wanted if pair not in cached_pairs]

    if missing:
        if not api_key:
            warnings.append("No TWELVE_DATA_KEY found in your .env file, so no new rates were fetched.")
        else:
            new_rows, errors = fetch_quotes(missing, api_key)
            warnings.extend(errors)
            if new_rows:
                db.save_fx_rates(conn, date, new_rows)

    # Re-read from the database so the result always matches what's saved.
    rows = [row for row in db.load_fx_rates(conn, date) if row["pair"] in wanted]
    return sort_by_biggest_move(rows), warnings
