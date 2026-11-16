"""
config.py: settings you can edit without touching the rest of the code.

To track a new currency, add a line to CURRENCIES below.
The pair must be quoted as "USD/XXX" (how many units of local currency 1 US dollar buys).
"""

# The EM currencies the desk tracks.
#   pair     = the symbol Twelve Data uses
#   country  = shown in tables (and used later for the Big Mac comparison)
#   currency = a friendly name for the local currency
CURRENCIES = [
    {"pair": "USD/BRL", "country": "Brazil",       "currency": "real"},
    {"pair": "USD/MXN", "country": "Mexico",       "currency": "peso"},
    {"pair": "USD/INR", "country": "India",        "currency": "rupee"},
    {"pair": "USD/ZAR", "country": "South Africa", "currency": "rand"},
    {"pair": "USD/TRY", "country": "Turkey",       "currency": "lira"},
    {"pair": "USD/CNY", "country": "China",        "currency": "yuan"},
    {"pair": "USD/KRW", "country": "South Korea",  "currency": "won"},
    {"pair": "USD/IDR", "country": "Indonesia",    "currency": "rupiah"},
    {"pair": "USD/CLP", "country": "Chile",        "currency": "peso"},
    {"pair": "USD/COP", "country": "Colombia",     "currency": "peso"},
]

# The SQLite database file. It is created automatically the first time you run the app.
DB_PATH = "desk.db"

# Your timezone, so "today" means your today (matters for the online website, whose
# servers run on UTC). Names: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
TIMEZONE = "America/New_York"

# Twelve Data's free plan allows 8 "credits" per minute, and each currency pair
# costs 1 credit. So we ask for at most 8 pairs at a time, then wait a minute.
TWELVE_DATA_MAX_PER_MINUTE = 8


# ---------------------------------------------------------------------------
# Phase 2: news and the brief
# ---------------------------------------------------------------------------

# A headline is kept for the brief only if it mentions one of these words.
# Matching ignores upper/lower case and only matches whole words
# (so "Fed" matches "Fed" but not "fedora"). Add or remove words freely.
NEWS_KEYWORDS = [
    # Countries we track
    "Brazil", "Mexico", "India", "South Africa", "Turkey", "Turkiye", "China",
    "South Korea", "Korea", "Indonesia", "Chile", "Colombia",
    # Currency codes and names (skipping "real" and "peso" alone: too many false matches)
    "BRL", "MXN", "INR", "ZAR", "TRY", "CNY", "yuan", "renminbi", "KRW", "won",
    "IDR", "rupiah", "CLP", "COP", "rupee", "rand", "lira",
    # Central banks
    "central bank", "Banxico", "RBI", "Reserve Bank of India", "SARB", "PBOC",
    "People's Bank of China", "Bank of Korea", "Bank Indonesia", "Copom",
    # Big global drivers of EM currencies
    "emerging market", "emerging markets", "Fed", "Federal Reserve", "FOMC",
    "Powell", "dollar", "oil", "crude", "Brent", "OPEC", "tariff", "tariffs",
]

# How many matching headlines to show and send to Claude.
MAX_HEADLINES = 12

# Which Claude model writes the brief, and how hard it thinks.
# "low" effort is plenty for a short morning note and keeps the cost to a few cents.
CLAUDE_MODEL = "claude-opus-5-5"
CLAUDE_EFFORT = "low"


# ---------------------------------------------------------------------------
# Phase 3: Prices Around the World
# ---------------------------------------------------------------------------

# The items to price in every tracked country.
#   source = "economist" uses The Economist's Big Mac data (downloaded automatically).
#   source = a CSV file path uses your own prices. Copy items/_template.csv, fill it in,
#            then add a line here, e.g.:
#            {"name": "iPhone", "source": "items/iphone.csv"},
#   phrase = (optional) how the item reads in a sentence, e.g. "a liter of gasoline"
#   note   = (optional) a caveat shown under the table
ITEMS = [
    {"name": "Big Mac", "source": "economist"},
    {"name": "iPhone 17", "source": "items/iphone.csv", "phrase": "an iPhone 17",
     "note": "256 GB model. The US price excludes sales tax; other countries include VAT. See items/SOURCES.md."},
    {"name": "Netflix Standard", "source": "items/netflix.csv", "phrase": "a month of Netflix Standard",
     "note": "Monthly price of the Standard plan (no ads). Not available in China. See items/SOURCES.md."},
    {"name": "Gasoline (1 liter)", "source": "items/gasoline.csv", "phrase": "a liter of gasoline",
     "note": "Regular 95-octane. Some prices are several months old; see items/SOURCES.md."},
]

# Re-download The Economist's data only if our saved copy is older than this.
# (They only update it twice a year, in January and July.)
BIG_MAC_CACHE_DAYS = 30


# ---------------------------------------------------------------------------
# Phase 4: Math drill
# ---------------------------------------------------------------------------

# How many questions per drill (the plan says 5 to 10).
DRILL_QUESTIONS = 7

# Size of the position in P&L questions, in US dollars.
DRILL_PNL_NOTIONAL = 1_000_000
