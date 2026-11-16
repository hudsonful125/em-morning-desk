"""
data/news.py: gets market and forex headlines from Finnhub, then picks the ones
that matter for an EM FX desk and gives each a simple mood score.

Finnhub's /news endpoint returns the latest ~100 stories for a category.
We ask for two categories ("general" and "forex") = 2 API calls per day.
Everything is saved in SQLite, so re-running the same day costs no API calls.

The mood score ("sentiment") is a deliberately simple keyword count done in Python:
each positive word adds 1, each negative word subtracts 1. It's rough, but it's
transparent: you can see exactly why a headline got its label.
"""

import re

import requests

import config
import db

NEWS_URL = "https://finnhub.io/api/v1/news"
CATEGORIES = ["general", "forex"]

# Words that usually signal good news (for risk assets / EM currencies) or bad news.
POSITIVE_WORDS = [
    "rally", "rallies", "rallied", "gain", "gains", "gained", "rise", "rises", "rose",
    "surge", "surges", "surged", "jump", "jumps", "jumped", "climb", "climbs", "climbed",
    "rebound", "rebounds", "recover", "recovers", "boost", "boosts", "strong", "stronger",
    "strengthen", "strengthens", "beat", "beats", "upgrade", "upgrades", "optimism",
    "record high", "easing", "eases", "deal", "inflows", "growth",
]
NEGATIVE_WORDS = [
    "fall", "falls", "fell", "drop", "drops", "dropped", "slump", "slumps", "slumped",
    "plunge", "plunges", "plunged", "slide", "slides", "slid", "tumble", "tumbles",
    "sink", "sinks", "sank", "weak", "weaker", "weaken", "weakens", "loss", "losses",
    "miss", "misses", "downgrade", "downgrades", "fear", "fears", "worry", "worries",
    "risk", "risks", "crisis", "default", "sell-off", "selloff", "outflows", "recession",
    "slowdown", "war", "sanctions", "tariff", "tariffs", "inflation",
]


# ---------------------------------------------------------------------------
# Matching and scoring (pure Python, easy to test)
# ---------------------------------------------------------------------------

def _word_pattern(words):
    """
    Build one regular expression that finds any of `words` as whole words, ignoring case.
    \\b means "word boundary", so "Fed" won't match inside "fedora".
    """
    escaped = [re.escape(w) for w in words]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)


KEYWORD_PATTERN = _word_pattern(config.NEWS_KEYWORDS)
POSITIVE_PATTERN = _word_pattern(POSITIVE_WORDS)
NEGATIVE_PATTERN = _word_pattern(NEGATIVE_WORDS)


def matched_keywords(headline):
    """Return the tracked keywords found in a headline, e.g. ['Brazil', 'central bank']."""
    found = KEYWORD_PATTERN.findall(headline)
    # Remove duplicates but keep the order they appeared in
    unique = []
    for word in found:
        if word.lower() not in [u.lower() for u in unique]:
            unique.append(word)
    return unique


def sentiment(headline):
    """
    Score a headline: +1 per positive word, -1 per negative word.
    Returns (label, score), e.g. ("negative", -2).
    """
    score = len(POSITIVE_PATTERN.findall(headline)) - len(NEGATIVE_PATTERN.findall(headline))
    if score > 0:
        return "positive", score
    if score < 0:
        return "negative", score
    return "neutral", 0


def pick_relevant(items, limit=None):
    """
    From all of today's headlines, keep the ones that mention a tracked keyword,
    drop duplicates (the same headline can appear in both categories),
    and add 'keywords' and 'sentiment' to each. Newest first.
    """
    limit = limit or config.MAX_HEADLINES
    seen = set()
    picked = []
    for item in sorted(items, key=lambda i: i.get("published") or 0, reverse=True):
        headline = item["headline"].strip()
        keywords = matched_keywords(headline)
        if not keywords or headline.lower() in seen:
            continue
        seen.add(headline.lower())
        label, score = sentiment(headline)
        picked.append(dict(item, keywords=keywords, sentiment=label, score=score))
        if len(picked) >= limit:
            break
    return picked


# ---------------------------------------------------------------------------
# Talking to the Finnhub API
# ---------------------------------------------------------------------------

def parse_news(data, category):
    """Turn Finnhub's JSON list into our simple dicts, skipping anything malformed."""
    items = []
    if not isinstance(data, list):
        return items
    for story in data:
        if not isinstance(story, dict) or not story.get("headline") or story.get("id") is None:
            continue
        items.append({
            "id": story["id"],
            "category": category,
            "headline": story["headline"],
            "source": story.get("source", ""),
            "url": story.get("url", ""),
            "published": story.get("datetime", 0),
        })
    return items


def fetch_news(api_key):
    """Download the latest general + forex news. Returns (items, errors)."""
    items, errors = [], []
    for category in CATEGORIES:
        try:
            response = requests.get(
                NEWS_URL, params={"category": category, "token": api_key}, timeout=20
            )
            if response.status_code == 401:
                errors.append("Finnhub rejected the API key. Check FINNHUB_KEY in your .env file.")
                break
            response.raise_for_status()
            items.extend(parse_news(response.json(), category))
        except (requests.RequestException, ValueError) as error:
            errors.append(f"Could not get {category} news from Finnhub: {error}")
    return items, errors


def get_news(conn, date, api_key, refresh=False):
    """
    Return (relevant_headlines, warnings) for the given date.
    Uses today's saved headlines if we have them; otherwise downloads and saves them.
    """
    warnings = []
    items = [] if refresh else db.load_news(conn, date)

    if not items:
        if not api_key:
            warnings.append("No FINNHUB_KEY found in your .env file, so the brief has no headlines.")
        else:
            items, errors = fetch_news(api_key)
            warnings.extend(errors)
            if items:
                db.save_news(conn, date, items)

    return pick_relevant(items), warnings
