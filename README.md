# EM Morning Desk

A ~10-minute daily routine that trains you to think like an emerging-markets FX analyst:
a morning brief, a Big Mac price comparison, and a mental-math drill, all built from that
morning's real numbers.

**Status:** All 6 phases are built: the terminal app, the web dashboard, extra price items, a central bank calendar, and a weekday-morning email. Run `python3 main.py` each morning, or open the dashboard (see below).

## One-time setup

1. **Install Python 3.9 or newer.** Check with `python3 --version` (Mac) or `python --version` (Windows).
2. **Get your API keys:**
   - Twelve Data (free): https://twelvedata.com → Dashboard → API Keys. Used for exchange rates.
   - Finnhub (free): https://finnhub.io → the key is on your dashboard. Used for headlines.
   - Anthropic (pay-as-you-go): https://console.anthropic.com → Billing (add a few dollars) → API Keys.
     Used for Claude to write the brief; each brief costs a few cents.
3. **Open a terminal in this folder** (`em-morning-desk/`).
4. **(Recommended) make a virtual environment** so this project's libraries stay separate:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Mac/Linux
   .venv\Scripts\activate           # Windows
   ```
5. **Install the libraries:**
   ```bash
   pip install -r requirements.txt
   ```
6. **Add your keys** to a file named `.env` in this folder, one per line:
   ```
   TWELVE_DATA_KEY=...
   FINNHUB_KEY=...
   ANTHROPIC_API_KEY=...
   ```
   From Terminal you can add a line with `echo "FINNHUB_KEY=yourkey" >> .env`.
   Use **two** `>>` to add a line; a single `>` wipes the file first. Never share or upload `.env`.

## Running it

```bash
python3 main.py                    # the full morning routine: Brief -> Prices -> Drill
python3 main.py --fx               # today's EM currency moves, biggest mover first
python3 main.py --brief            # top movers, EM headlines, and Claude's morning note
python3 main.py --brief --refresh  # re-download everything and rewrite the brief
python3 main.py --prices           # Big Mac priced in USD at today's rates: cheap vs expensive currencies
python3 main.py --drill            # timed mental-math quiz built from today's numbers
python3 main.py --stats            # your drill history: accuracy by type, speed trend, streak
python3 -m pytest                  # run the tests (no API calls, no key needed)
```

The first run of the day downloads the rates. Twelve Data's free plan allows 8 pairs per
minute and we track 10, so **the first run waits about a minute** between two batches.
Later runs that day read from `desk.db` instantly and spend no credits. The same goes for
headlines and the brief: Claude only writes one brief per day unless you add `--refresh`.

## How the brief stays accurate

Python calculates every number (moves, top movers, the headline mood count) and hands
Claude a short fact sheet. Claude only writes the sentences and is told never to invent a
figure. The headline mood is a simple keyword count (words like "rally" vs "slump") in
`data/news.py`, so you can see exactly why a headline was marked positive or negative.

## Prices Around the World

`--prices` takes The Economist's Big Mac prices (free data, updated each January and July)
and converts them at **today's** exchange rates:

- **Price in USD** = local price ÷ today's USD/XXX rate
- **vs US** = (price in USD ÷ US price) − 1. Negative = the currency looks undervalued.
- **Implied PPP rate** = local price ÷ US price: the exchange rate that would make a Big Mac
  cost the same as in the US. Compare it with today's actual rate.

The data is saved in `cache/` and re-downloaded only when it's over 30 days old.

It also compares an **iPhone 17**, **Netflix Standard** and **a liter of gasoline**, from
the CSV files in `items/` (sources and caveats in `items/SOURCES.md`). Update those files
whenever prices change. To add another item, copy `items/_template.csv`, fill in local
prices, and add a line to `ITEMS` in `config.py`.

## The math drill

`--drill` asks 7 questions (change `DRILL_QUESTIONS` in `config.py`) built from today's
rates: % changes, currency conversions, basis points, inverse quotes, P&L, and quick
arithmetic. Python calculates every answer from the same rounded numbers shown in the
question and accepts answers within a small tolerance (about 1%). You can type `20k`,
`$4.17` or `0.5%`. Each answer is timed and saved in `desk.db`, and question types you miss
or answer slowly come up more often next time.

## The web dashboard

The same desk as a web page, with charts and a clickable drill:

```bash
python3 -m pip install streamlit     # once
python3 -m streamlit run app.py      # every time
```

Your browser opens at http://localhost:8501. It only runs on your computer. Use the menu on
the left: Brief, Prices, Drill, Stats. It shares `desk.db` with `main.py`, so drills done in
the browser count in `--stats` too. To stop it, click on Terminal and press Control + C.

## The website online (Streamlit Community Cloud, free)

The same website at a public web address anyone can open from any device, no Terminal.

1. The code lives in a public GitHub repo. `.env` and `desk.db` are never uploaded, so your
   keys stay private. Visitors can read the code but only you can change it.
2. At https://share.streamlit.io, sign in with GitHub, click **Create app**, pick the repo,
   branch `main`, main file `app.py`. Under **Advanced settings**, paste your keys into
   **Secrets** like this:
   ```toml
   TWELVE_DATA_KEY = "..."
   FINNHUB_KEY = "..."
   ANTHROPIC_API_KEY = "..."
   ADMIN_PASSWORD = "a-password-only-you-know"
   ```
   `ADMIN_PASSWORD` unlocks the 🔄 Refresh button, which asks Claude for a new brief (a few
   cents a click). Everyone else sees the brief that's already saved for the day.
   Optional: add `APP_PASSWORD = "..."` if you ever want a password to open the site at all.

Without accounts (below), the Drill and Stats pages ask for a name, so each person keeps
their own scores. Use the same name each time.

### Accounts with email and password (Supabase, free)

With this set up, everyone has to create an account (any email address) and sign in before
using the website. Each person's drill scores are saved to their own account and kept for good,
even when Streamlit restarts the app. Passwords are stored securely by Supabase; nobody can read them.

1. Go to https://supabase.com, click **Start your project**, and sign in with GitHub.
2. Click **New project**. Name it `em-morning-desk`, click **Generate a password** (you won't
   need it again), pick the region closest to you, and click **Create new project**.
3. When it's ready, open **SQL Editor** (left menu), paste everything from
   `supabase_setup.sql`, and click **Run**. It should say "Success. No rows returned".
4. Open **Authentication → Sign In / Providers → Email**, turn **off** "Confirm email", and
   click **Save**. (Otherwise people must click a link in an email first, and Supabase's free
   email sender only sends a few per hour.)
5. Click **Connect** at the top (or Project Settings → API Keys) and copy the **Project URL**
   and the **publishable key** (starts with `sb_publishable_`; older projects call it the
   "anon public" key).
6. In Streamlit's **Secrets**, add (above any `[section]` line):
   ```toml
   SUPABASE_URL = "https://xxxx.supabase.co"
   SUPABASE_KEY = "sb_publishable_..."
   ```

To see or delete accounts, open **Authentication → Users** in Supabase. Remove the two
lines from Secrets to turn accounts off again (the site then asks for a name instead).
People stay signed in until they close the tab or click **Sign out**.

Good to know: the online app has its own database, separate from your Mac. Drill history
there can reset when Streamlit restarts the app (after it sleeps from a few days of no use).
The weekday email still comes from your Mac.

## The brief by email every weekday morning (free)

1. (Optional, for email) Set up a Gmail app password. The steps are at the top of
   `modules/emailer.py`. Then add `EMAIL_ADDRESS` and `EMAIL_APP_PASSWORD` to `.env`.
   Without them you still get a Mac notification and the file in `briefs/`.
2. Turn on the schedule (weekdays at 7:30 am; change the time at the top of the script):
   ```bash
   bash schedule/install_mac.sh
   ```
   It runs once straight away as a test and shows you the log.
3. To turn it off: `bash schedule/uninstall_mac.sh`

If the Mac is asleep at 7:30, the brief runs when it wakes. Each morning's log is in
`~/Library/Logs/em-morning-desk.log`. The only cost is Claude writing the brief (a few cents).

## Central bank calendar

`data/central_bank_calendar.csv` lists upcoming EM rate decisions. The next 14 days show in
the brief, and Claude mentions them in "What to watch". There's no free API for these, so
add next year's dates to the CSV as the central banks publish them. Rows marked
`cbrates.com` came from a third-party list rather than the bank's own site.

## The full routine, stats and saved briefs

Plain `python3 main.py` shows the brief, then the Big Mac table, then asks whether to start
the drill. Press return to start it, or type `s` and press return to skip it.

Every time the brief runs, a copy is saved as `briefs/YYYY-MM-DD.md` (for example
`briefs/2026-11-16.md`), so you can re-read past mornings in any text editor.

`--stats` shows your accuracy and average time for each question type (weakest first), your
score for recent days, whether you're getting faster than last week, and your streak (days
in a row you've done the drill).

## Reading the table

Pairs are quoted as **USD/XXX**: how many units of local currency one dollar buys.
If USD/BRL goes **up**, a dollar buys more reais, so the **real weakened** (shown in red).
If it goes **down**, the real **strengthened** (green).

## Editing what's tracked

Open `config.py` and add or remove lines in `CURRENCIES`. To change which headlines count
as relevant, edit `NEWS_KEYWORDS` in the same file.

## Project layout

```
config.py      settings you can edit (currency list, database file)
main.py        the entry point you run
db.py          saves and loads data in desk.db (SQLite)
data/fx.py     gets rates from Twelve Data and does the % change math
data/news.py   gets headlines from Finnhub, filters them, scores their mood
modules/brief.py  builds the fact sheet and asks Claude to write the note
data/bigmac.py    downloads/caches Big Mac prices and reads your own item CSVs
modules/prices.py USD prices, over/undervaluation, implied PPP, the news tie-in
items/            your own item price files (start from _template.csv)
modules/drill.py  builds, times and grades the drill; picks more of your weak spots
app.py            the web dashboard (Streamlit)
modules/routine.py builds one morning's brief (used by main.py, app.py and the schedule)
modules/usd_outlook.py USD vs EM history (1M/1Y/5Y) and the long-term scenarios
data/fx_history.py monthly rate history from Twelve Data (cached a week in cache/)
data/policy_rates.csv central bank rates used by the Rate gap scenario (edit when banks move)
modules/usd_trade.py the dollar's share of each country's trade (data/usd_invoicing.csv)
modules/accounts.py email + password accounts and saved drill scores on the website (Supabase)
modules/emailer.py sends the brief through Gmail
morning_job.py    the hands-off brief the schedule runs
schedule/         turn the weekday-morning schedule on and off
data/cb_calendar.py + central_bank_calendar.csv  upcoming rate decisions
modules/stats.py  drill history: accuracy by type, speed trend, streak
modules/archive.py saves each day's brief to briefs/
briefs/           your saved daily briefs (created on the first run)
tests/         automatic checks of the math, using saved sample data
```
