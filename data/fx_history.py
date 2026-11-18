"""
data/fx_history.py: monthly exchange-rate history (about 6 years) for the USD vs EM pages,
plus the commodity funds in config.COMMODITIES (for the Carry & Commodities page).

Twelve Data's /time_series endpoint gives one closing price per month. Each pair costs
1 credit, the same as today's quotes, so we fetch at most 8 pairs a minute and keep a copy
in cache/fx_history.json. The copy is reused for a week, since month-end prices don't change.
"""

import json
import os
import time

import requests

import config

SERIES_URL = "https://api.twelvedata.com/time_series"
CACHE_PATH = os.path.join("cache", "fx_history.json")
CACHE_DAYS = 7
MONTHS = 72  # 6 years of month-end closes


def parse_series(data):
    """Twelve Data's reply for one pair -> [(date 'YYYY-MM-DD', close), ...] oldest first."""
    values = data.get("values") or []
    points = []
    for v in values:
        try:
            points.append((v["datetime"][:10], float(v["close"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(points)


def fetch_history(pairs, api_key, sleep=time.sleep):
    """Download monthly closes for each pair. Returns ({pair: points}, errors)."""
    history, errors = {}, []
    batch_size = config.TWELVE_DATA_MAX_PER_MINUTE
    for start in range(0, len(pairs), batch_size):
        batch = pairs[start:start + batch_size]
        if start:
            sleep(61)  # stay under the free plan's 8 credits a minute
        for attempt in range(2):
            try:
                reply = requests.get(SERIES_URL, timeout=30, params={
                    "symbol": ",".join(batch), "interval": "1month",
                    "outputsize": MONTHS, "apikey": api_key}).json()
            except (requests.RequestException, ValueError) as error:
                errors.append(f"Couldn't reach Twelve Data for the history: {error}")
                break
            # Hit the per-minute limit (e.g. the brief just used it)? Wait once and retry.
            if reply.get("code") == 429 and attempt == 0:
                sleep(61)
                continue
            if reply.get("status") == "error" and "values" not in reply:
                errors.append(f"Twelve Data: {reply.get('message', 'unknown error')}")
                break
            replies = {batch[0]: reply} if len(batch) == 1 else reply
            for pair in batch:
                points = parse_series(replies.get(pair) or {})
                if points:
                    history[pair] = points
                else:
                    errors.append(f"No history for {pair}")
            break
    return history, errors


def wanted_symbols():
    """The 10 currency pairs plus the commodity funds (see config.COMMODITIES)."""
    return [c["pair"] for c in config.CURRENCIES] + [c["symbol"] for c in config.COMMODITIES]


def get_history(api_key, refresh=False):
    """Monthly history for all tracked pairs, from the cache when it's fresh. Returns (history, warnings)."""
    cached = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            cached = json.load(f)
        fresh = time.time() - os.path.getmtime(CACHE_PATH) < CACHE_DAYS * 86400
        complete = all(symbol in cached for symbol in wanted_symbols())
        if fresh and complete and not refresh:
            return {k: [tuple(p) for p in v] for k, v in cached.items()}, []
    if not api_key:
        return ({k: [tuple(p) for p in v] for k, v in cached.items()},
                ["No TWELVE_DATA_KEY, so the rate history couldn't be downloaded."])
    history, errors = fetch_history(wanted_symbols(), api_key)
    # Keep anything we had before that didn't come back this time (e.g. one symbol failed).
    history = dict({k: [tuple(p) for p in v] for k, v in cached.items()}, **history)
    if history:
        os.makedirs("cache", exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f)
    return history, errors
