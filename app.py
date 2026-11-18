"""
app.py: the EM Morning Desk as a web page in your browser (Phase 6).

Start it from the em-morning-desk folder with:

    python3 -m streamlit run app.py

Your browser opens at http://localhost:8501. The page runs on YOUR computer only;
nobody else can see it. To stop it, go back to Terminal and press Control + C.

It uses exactly the same code as main.py (same database, same math, same brief),
so anything you do here also shows up in `python3 main.py --stats`, and vice versa.

How Streamlit works, in one paragraph: every time you click a button or submit an
answer, Streamlit re-runs this whole file from top to bottom and redraws the page.
Anything that has to survive between clicks (like which drill question you're on)
is kept in `st.session_state`, a dictionary that lasts until you close the tab.
"""

import hmac
import json
import os
import time
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import config
import db
from data import bigmac, fx, fx_history
from modules import accounts, brief, drill, prices, routine, stats, usd_outlook, usd_trade

load_dotenv()  # on your Mac: keys from .env. Online, Streamlit's "Secrets" provide them instead.

# Online servers run on UTC time. Use your own timezone so "today" flips at your midnight.
if hasattr(time, "tzset"):
    os.environ["TZ"] = config.TIMEZONE
    time.tzset()

st.set_page_config(page_title="EM Morning Desk", page_icon="🌎", layout="wide")

TODAY = date.today().isoformat()


def check_password():
    """
    If APP_PASSWORD is set (in .env or Streamlit's Secrets), ask for it before showing anything.
    This stops anyone who finds the link from using your API keys. No password set = no prompt.
    """
    password = os.getenv("APP_PASSWORD")
    if not password or st.session_state.get("signed_in"):
        return True
    st.title("🌎 EM Morning Desk")
    typed = st.text_input("Password", type="password")
    if typed:
        if hmac.compare_digest(typed, password):
            st.session_state.signed_in = True
            st.rerun()
        st.error("Wrong password.")
    return False

# Chart colours: blue = cheaper than the US (undervalued), red = pricier (overvalued)
BLUE, RED = "#2a78d6", "#e34948"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def connect():
    """A fresh database connection for this run of the page."""
    return db.connect()


def md(text):
    """Escape $ signs, which Streamlit would otherwise read as maths formatting."""
    return text.replace("$", "\\$")


def show_warnings(warnings):
    for message in warnings:
        st.warning(message)


def get_fx_rows(conn, refresh=False):
    """Today's rates from desk.db, downloading them first if needed (the first time takes ~1 minute)."""
    with st.spinner("Getting today's exchange rates (the first time each day takes about a minute)..."):
        rows, warnings = fx.get_fx_rates(conn, TODAY, os.getenv("TWELVE_DATA_KEY"), refresh=refresh)
    show_warnings(warnings)
    return rows


def fx_table(rows):
    """The FX moves as a table, biggest mover first."""
    names = {c["pair"]: c for c in config.CURRENCIES}
    table = pd.DataFrame([{
        "Pair": r["pair"],
        "Country": names.get(r["pair"], {}).get("country", ""),
        "Prev close": r["prev_close"],
        "Latest": r["rate"],
        "% change": r["pct_change"],
        "Local currency": f"{names.get(r['pair'], {}).get('currency', '')} {fx.direction_word(r['pct_change'])}",
    } for r in rows])

    def colour(value):
        # Red when the local currency weakened (USD/XXX up), green when it strengthened
        return "color: #d03b3b" if value > 0 else "color: #0ca30c" if value < 0 else ""

    styled = table.style.format({"Prev close": "{:,.4f}", "Latest": "{:,.4f}", "% change": "{:+.2f}%"})
    paint = getattr(styled, "map", None) or styled.applymap  # older pandas calls it applymap
    styled = paint(colour, subset=["% change"])
    st.dataframe(styled, hide_index=True, width="stretch")
    st.caption("USD/XXX up = the local currency weakened (a dollar buys more of it).")


# ---------------------------------------------------------------------------
# Page 1: the brief
# ---------------------------------------------------------------------------

def refresh_button():
    """
    The Refresh button asks Claude for a new brief, which costs a few cents per click.
    If ADMIN_PASSWORD is set (in Streamlit's Secrets), only someone who types it can refresh.
    With no ADMIN_PASSWORD (e.g. on your own Mac), the button always works.
    """
    admin = os.getenv("ADMIN_PASSWORD")
    if admin and not st.session_state.get("is_admin"):
        typed = st.sidebar.text_input("Admin password (to refresh)", type="password")
        if typed and hmac.compare_digest(typed, admin):
            st.session_state.is_admin = True
            st.rerun()
        elif typed:
            st.sidebar.error("Wrong admin password.")
        return False
    return st.sidebar.button("🔄 Refresh today's data",
                             help="Re-download rates and headlines and ask Claude for a new brief (a few cents)")


def page_brief():
    st.header(f"📰 The Brief: {date.today():%A %B %d}")
    refresh = refresh_button()
    with st.spinner("Getting today's rates, headlines and brief (the first time each day takes about a minute)..."):
        r = routine.make_brief(connect(), refresh=refresh)
    show_warnings(r["warnings"])
    if not r["fx_rows"]:
        st.error(r["error"])
        return

    left, right = st.columns([3, 2])
    with left:
        st.subheader("📊 Overnight moves vs USD")
        fx_table(r["fx_rows"])
    with right:
        st.subheader("Top movers")
        for m in r["summary"]["top_movers"]:
            dot = "🔴" if m["direction"] == "weakened" else "🟢"
            st.markdown(f"{dot} {brief.describe_move(m)}")
        st.subheader("🏦 Central bank decisions")
        st.caption("Next 14 days, from data/central_bank_calendar.csv")
        for line in r["meetings"] or ["None scheduled."]:
            st.markdown(f"- {md(line)}")

    if r["error"]:
        st.error(r["error"])
    else:
        st.subheader("📝 The note")
        st.markdown(md(r["text"]))
        st.caption(f"Numbers calculated in Python; words written by Claude. Saved to briefs/{TODAY}.md")

    st.subheader("Headlines")
    if r["headlines"]:
        mood = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}
        for h in r["headlines"]:
            title = f"[{h['headline']}]({h['url']})" if h.get("url") else h["headline"]
            st.markdown(md(f"{mood[h['sentiment']]} {title} *({h['source']})*"))
        st.caption("🟢 positive · 🔴 negative · ⚪ neutral, from a simple keyword count (see data/news.py).")
    else:
        st.write("No matching headlines today.")


# ---------------------------------------------------------------------------
# Page 2: prices around the world
# ---------------------------------------------------------------------------

def valuation_chart(table_rows, item_name):
    """Horizontal bars: how much cheaper (blue, left) or pricier (red, right) than in the US."""
    data = pd.DataFrame([{
        "Country": r["country"],
        "vs US (%)": round(r["valuation_pct"], 1),
        "Price in USD": round(r["usd_price"], 2),
        "Looks": "undervalued" if r["valuation_pct"] < 0 else "overvalued",
    } for r in table_rows])

    bars = alt.Chart(data).mark_bar(cornerRadiusEnd=4, height=16).encode(
        x=alt.X("vs US (%):Q", title=f"{item_name} price vs the US (%)"),
        y=alt.Y("Country:N", sort=alt.SortField("vs US (%)"), title=None),
        color=alt.Color("Looks:N", scale=alt.Scale(domain=["undervalued", "overvalued"], range=[BLUE, RED]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["Country", "Price in USD", "vs US (%)", "Looks"],
    )
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="gray").encode(x="x:Q")
    st.altair_chart((bars + zero).properties(height=alt.Step(28)))


def page_prices():
    st.header("🌍 Prices Around the World")
    conn = connect()
    fx_rows = get_fx_rows(conn)
    if not fx_rows:
        st.error("No FX data available, so prices can't be converted today.")
        return

    for item in config.ITEMS:
        name = item["name"]
        local_prices, price_date, warnings = bigmac.get_item_prices(item)
        show_warnings(warnings)
        table_rows = prices.build_price_table(fx_rows, local_prices)
        if not table_rows:
            continue

        st.subheader(f"{name} at today's exchange rates")
        st.info(md(prices.news_tie_in(table_rows, name, item.get("phrase"))))
        valuation_chart(table_rows, name)

        table = pd.DataFrame([{
            "Country": r["country"],
            "Local price": f"{r['local_price']:,.2f} {r['code']}",
            "Today's rate": round(r["rate"], 2),
            "Price in USD": round(r["usd_price"], 2),
            "vs US (%)": round(r["valuation_pct"], 1),
            "Implied PPP rate": round(r["implied_ppp"], 2),
        } for r in table_rows])
        st.dataframe(table, hide_index=True, width="stretch",
                     column_config={"Price in USD": st.column_config.NumberColumn(format="$%.2f"),
                                    "vs US (%)": st.column_config.NumberColumn(format="%+.1f%%")})
        source = " (The Economist updates them twice a year)" if item["source"] == "economist" else ""
        st.caption(f"US price: ${local_prices['USD']:.2f}. Negative = cheaper than the US, so the currency looks "
                   f"undervalued. Implied PPP rate = the USD/XXX rate that would make a {name} cost the same "
                   f"as in the US. {name} prices are from {price_date or 'an unknown date'}{source}; "
                   f"exchange rates are today's. {item.get('note', '')}")
        st.divider()


# ---------------------------------------------------------------------------
# Page: USD vs emerging markets, and long-term USD scenarios
# ---------------------------------------------------------------------------

SCENARIO_NOTES = {
    "Trend": "the last 5 years' average yearly move keeps going",
    "Rate gap": "the rate moves by the interest-rate difference each year, the way forward rates are priced",
    "Fair value": "the rate drifts toward the Big Mac fair (PPP) rate, closing half the gap every 5 years",
}


def get_history():
    with st.spinner("Getting 6 years of monthly exchange rates (the first time takes about a minute)..."):
        history, warnings = fx_history.get_history(os.getenv("TWELVE_DATA_KEY"))
    show_warnings(warnings)
    return history


def page_usd():
    st.header("💵 The Dollar vs Emerging Markets")
    st.caption("Pairs are USD/XXX, so a positive % means the dollar got stronger (it buys more local currency).")
    history = get_history()
    if not history:
        st.error("No exchange-rate history available yet. Check the Twelve Data key and try again in a minute.")
        return
    names = {c["pair"]: c for c in config.CURRENCIES}
    rows = usd_outlook.changes(history)

    # --- Looking back -------------------------------------------------------------
    st.subheader("How the dollar has done")
    cols = st.columns(3)
    for col, label in zip(cols, usd_outlook.PERIODS):
        avg = usd_outlook.basket_average(rows, label)
        col.metric(f"Dollar vs EM basket, {label}", "n/a" if avg is None else f"{avg:+.1f}%",
                   help="Equal-weighted average of the dollar's move against the 10 currencies.")

    table = pd.DataFrame([{
        "Country": names[r["pair"]]["country"], "Pair": r["pair"], "Latest": r["latest"],
        **{label: r[label] for label in usd_outlook.PERIODS},
    } for r in rows]).sort_values("5 years", ascending=False)
    fmt = {label: st.column_config.NumberColumn(format="%+.1f%%") for label in usd_outlook.PERIODS}
    st.dataframe(table, hide_index=True, width="stretch",
                 column_config={"Latest": st.column_config.NumberColumn(format="%,.4f"), **fmt})

    chart_rows = [{"Month": day, "Value": value, "Country": names[pair]["country"]}
                  for pair, points in history.items() for day, value in usd_outlook.rebased(points)]
    chosen = st.multiselect("Compare (5 years, start = 100; higher = stronger dollar)",
                            [c["country"] for c in config.CURRENCIES],
                            default=["Brazil", "Mexico", "India", "South Africa"])
    data = pd.DataFrame([r for r in chart_rows if r["Country"] in chosen])
    if not data.empty:
        line = alt.Chart(data).mark_line().encode(
            x=alt.X("Month:T", title=None, axis=alt.Axis(format="%b %Y")),
            y=alt.Y("Value:Q", title="USD/XXX, start = 100 (higher = stronger dollar)", scale=alt.Scale(zero=False)),
            color=alt.Color("Country:N", legend=alt.Legend(orient="top", title=None)),
            tooltip=["Country", alt.Tooltip("Month:T", format="%b %Y"), alt.Tooltip("Value:Q", format=".1f")])
        st.altair_chart(line.properties(height=320))
    st.caption(f"Monthly closes from Twelve Data, latest month {rows[0]['as_of'][:7] if rows else 'n/a'}. "
               "Turkey's lira fell so far that it can stretch the chart; untick it to see the others.")

    # --- Looking ahead --------------------------------------------------------------
    st.subheader("Long-term USD scenarios")
    st.write("These are **what-if scenarios, not forecasts**. Each one follows a simple stated rule, "
             "so you can see how the answer depends on the assumption:")
    for name, note in SCENARIO_NOTES.items():
        st.markdown(f"- **{name}:** {note}.")

    rates, rate_dates = usd_outlook.load_policy_rates()
    today_rates = {r["pair"]: r["rate"] for r in db.load_fx_rates(connect(), TODAY)}
    big_mac, _, _ = bigmac.get_item_prices({"name": "Big Mac", "source": "economist"})
    us_big_mac = big_mac.get("USD")

    results = []
    for r in rows:
        pair = r["pair"]
        code = pair.split("/")[1]
        spot = today_rates.get(pair, r["latest"])
        ppp = prices.implied_ppp(big_mac[code], us_big_mac) if us_big_mac and code in big_mac else None
        paths = usd_outlook.scenarios(spot, r["cagr_5y"], rates.get(pair), rates.get("USD"), ppp)
        results.append({"pair": pair, "spot": spot, "paths": paths})

    horizon = st.radio("Years ahead", usd_outlook.HORIZONS, index=2, horizontal=True)
    scen_table = pd.DataFrame([{
        "Country": names[x["pair"]]["country"], "Today": x["spot"],
        **{name: usd_outlook.dollar_move(x["spot"], path[horizon]) for name, path in x["paths"].items()},
    } for x in results])
    st.dataframe(scen_table, hide_index=True, width="stretch",
                 column_config={"Today": st.column_config.NumberColumn(format="%,.4f"),
                                **{n: st.column_config.NumberColumn(f"{n} (%)", format="%+.1f%%")
                                   for n in SCENARIO_NOTES}})
    averages = {}
    for name in SCENARIO_NOTES:
        moves = [usd_outlook.dollar_move(x["spot"], x["paths"][name][horizon])
                 for x in results if name in x["paths"]]
        if moves:
            averages[name] = sum(moves) / len(moves)
    st.write("Dollar vs the EM basket in " + f"{horizon} year{'s' if horizon > 1 else ''}: " +
             ", ".join(f"**{n}** {v:+.1f}%" for n, v in averages.items()) + ".")

    country = st.selectbox("See one currency's path", [names[x["pair"]]["country"] for x in results])
    pick = next(x for x in results if names[x["pair"]]["country"] == country)
    past = history[pick["pair"]][-61:]
    last_day = date.fromisoformat(past[-1][0])
    lines = [{"Date": d, "USD/XXX": v, "Line": "History"} for d, v in past]
    for name, path in pick["paths"].items():
        lines.append({"Date": TODAY, "USD/XXX": pick["spot"], "Line": name})
        lines += [{"Date": last_day.replace(year=last_day.year + y).isoformat(), "USD/XXX": v, "Line": name}
                  for y, v in path.items()]
    chart = alt.Chart(pd.DataFrame(lines)).mark_line(point=True).encode(
        x=alt.X("Date:T", title=None, axis=alt.Axis(format="%Y")),
        y=alt.Y("USD/XXX:Q", title=f"{pick['pair']} (higher = stronger dollar)", scale=alt.Scale(zero=False)),
        color=alt.Color("Line:N", scale=line_colours(["History", *pick["paths"]]), legend=alt.Legend(orient="top", title=None)),
        strokeDash=alt.condition(alt.datum.Line == "History", alt.value([1, 0]), alt.value([5, 4])),
        tooltip=["Line", alt.Tooltip("Date:T", format="%b %Y"), alt.Tooltip("USD/XXX:Q", format=",.4f")])
    st.altair_chart(chart.properties(height=320))

    st.caption(f"Policy rates used: US {rates.get('USD')}% (Fed range midpoint), {country} "
               f"{rates.get(pick['pair'], 'n/a')}% (last changed {rate_dates.get(pick['pair'], 'n/a')}), "
               f"from data/policy_rates.csv (cbrates.com, checked Nov 2026; edit the file when banks move). "
               f"Fair value uses the latest Big Mac prices. Trend uses the last 5 years of monthly closes.")


# ---------------------------------------------------------------------------
# Page: the dollar's share of each country's trade (world map)
# ---------------------------------------------------------------------------

# Country outlines (Natural Earth, via the vega-datasets package), saved in the project so the
# map doesn't depend on another website.
WORLD_MAP = os.path.join("data", "world-110m.json")

# One fixed colour per line, so "History" always looks the same on every chart
COLOURS = {"History": "#555555", "Trend": RED, "Rate gap": "#e8a33d", "Fair value": BLUE, "Steady": "#8c6bb1"}


def line_colours(names):
    return alt.Scale(domain=names, range=[COLOURS[n] for n in names])


@st.cache_data
def world_outlines():
    with open(WORLD_MAP, encoding="utf-8") as f:
        return json.load(f)


def page_trade():
    st.header("🗺️ How Much Each Country Trades in Dollars")
    rows = usd_trade.load()
    if not rows:
        st.info("The world map is waiting for its data: the IMF's invoicing-currency dataset "
                "(the share of each country's exports and imports priced in US dollars). "
                "Once it's added as data/usd_invoicing.csv, the map appears here.")
        return

    kind = st.radio("Trade", ["Exports", "Imports"], horizontal=True)
    column = "usd_export_share" if kind == "Exports" else "usd_import_share"
    latest = usd_trade.latest_by_country(rows, column)
    data = pd.DataFrame([{"id": r["iso_num"], "Country": r["country"], "Share": r[column], "Year": r["year"]}
                         for r in latest])

    world = alt.InlineData(values=world_outlines(),
                           format=alt.DataFormat(type="topojson", feature="countries"))
    background = alt.Chart(world).mark_geoshape(fill="#e6e6e6", stroke="white", strokeWidth=0.5)
    shares = alt.Chart(world).mark_geoshape(stroke="white", strokeWidth=0.5).encode(
        color=alt.Color("Share:Q", title=f"% of {kind.lower()} in USD",
                        scale=alt.Scale(domain=[0, 100], scheme="blues")),
        tooltip=["Country:N", alt.Tooltip("Share:Q", format=".0f", title="% in USD"), "Year:Q"],
    ).transform_lookup(lookup="id", from_=alt.LookupData(data, "id", ["Country", "Share", "Year"])
    ).transform_filter("isValid(datum.Share)")
    st.altair_chart((background + shares).project("equalEarth").properties(height=420))
    st.caption(f"Grey = no data. Each country shows its latest available year "
               f"({int(data['Year'].min())} to {int(data['Year'].max())}). Source: IMF invoicing-currency "
               "dataset (Boz, Casas, Georgiadis, Gopinath, Le Mezo, Mehl and Nguyen).")

    st.subheader("Where is it heading? (scenarios, not forecasts)")
    country = st.selectbox("Country", list(data.sort_values("Country")["Country"]))
    iso3 = next(r["iso3"] for r in latest if r["country"] == country)
    points = usd_trade.history(rows, iso3, column)
    last_year = points[-1][0]
    targets = [last_year + 5, last_year + 10]
    paths = usd_trade.scenarios(points, targets)
    lines = [{"Year": y, "Share": v, "Line": "History"} for y, v in points]
    for name, path in paths.items():
        lines.append({"Year": last_year, "Share": points[-1][1], "Line": name})
        lines += [{"Year": y, "Share": v, "Line": name} for y, v in path.items()]
    chart = alt.Chart(pd.DataFrame(lines)).mark_line(point=True).encode(
        x=alt.X("Year:Q", axis=alt.Axis(format="d")),
        y=alt.Y("Share:Q", title=f"% of {kind.lower()} in USD", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color("Line:N", scale=line_colours(["History", *paths]), legend=alt.Legend(orient="top", title=None)),
        tooltip=["Line", "Year:Q", alt.Tooltip("Share:Q", format=".1f")])
    st.altair_chart(chart.properties(height=300))
    st.caption("Steady = the share stays at its latest level. Trend = the straight-line trend of the last "
               f"{usd_trade.TREND_YEARS} years continues (needs 3+ years of data). Real shares move with "
               "trade deals, sanctions and new payment systems, so treat these as what-ifs.")


# ---------------------------------------------------------------------------
# Accounts and whose drill scores
# ---------------------------------------------------------------------------

def sign_in_page():
    """
    When accounts are set up (SUPABASE_URL + SUPABASE_KEY in Secrets), everyone has to sign in
    or create an account before seeing anything. Returns True once they're signed in.
    """
    if not accounts.is_set_up() or st.session_state.get("account"):
        return True

    st.title("🌎 EM Morning Desk")
    st.write("A morning brief on emerging-market currencies, plus a timed FX math drill. "
             "Sign in, or create a free account with any email address.")
    sign_in_tab, sign_up_tab = st.tabs(["Sign in", "Create an account"])

    with sign_in_tab:
        with st.form("sign-in"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", type="primary"):
                try:
                    st.session_state.account = accounts.sign_in(email, password)
                    st.rerun()
                except accounts.AccountError as error:
                    st.error(str(error))

    with sign_up_tab:
        with st.form("sign-up"):
            email = st.text_input("Email", key="new-email")
            password = st.text_input(f"Password (at least {accounts.MIN_PASSWORD_LENGTH} characters)",
                                     type="password", key="new-password")
            again = st.text_input("Password again", type="password", key="new-password-again")
            if st.form_submit_button("Create account", type="primary"):
                problem = accounts.check_new_account(email, password, again)
                if problem:
                    st.error(problem)
                else:
                    try:
                        session = accounts.sign_up(email, password)
                        if session:
                            st.session_state.account = session
                            st.rerun()
                        st.success("Account created. Check your inbox for a confirmation email, "
                                   "then come back and sign in.")
                    except accounts.AccountError as error:
                        st.error(str(error))

    st.caption("Your password is stored securely by Supabase; nobody, including the site's owner, "
               "can read it. [Privacy](?page=privacy)")
    return False


def account_sidebar():
    """Shows who's signed in, with a Sign out button."""
    account = st.session_state.get("account")
    if account:
        st.sidebar.caption(f"Signed in as {account['email']}")
        if st.sidebar.button("Sign out"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


def player_name():
    """
    Whose drill scores to show and save on the shared website without accounts.
      - On the shared website (ADMIN_PASSWORD set): each person types a name.
      - On your Mac: "" (just you).
    Returns None if a name is needed but hasn't been typed yet.
    (With accounts set up this isn't used: scores belong to the signed-in account.)
    """
    if not os.getenv("ADMIN_PASSWORD"):
        return ""
    # Remembered in session_state (not as the widget's key) so it survives switching pages.
    typed = st.text_input("Your name", value=st.session_state.get("player_name", ""),
                          help="Your drill scores are saved under this name. Use the same name each time.")
    st.session_state.player_name = typed
    name = " ".join(typed.split()).lower()
    if not name:
        st.info("Type your name above (and press return) to see your own drill scores.")
        return None
    return name


def load_history(conn, player):
    """This person's drill history: from their account if signed in, otherwise from desk.db."""
    account = st.session_state.get("account")
    if account:
        try:
            return accounts.load_results(account)
        except accounts.AccountError as error:
            st.error(f"Couldn't load your past scores: {error}")
            return []
    return db.load_drill_results(conn, player=player)


def save_answer(conn, result, player):
    account = st.session_state.get("account")
    if account:
        try:
            accounts.save_result(account, TODAY, result)
        except accounts.AccountError as error:
            st.error(f"Couldn't save that answer to your account: {error}")
    else:
        db.save_drill_result(conn, TODAY, result, player=player)


def whose_scores():
    """The player name for desk.db (None = still waiting for a name). Accounts don't need one."""
    if st.session_state.get("account"):
        return st.session_state.account["email"]
    return player_name()


# ---------------------------------------------------------------------------
# Page 3: the drill
# ---------------------------------------------------------------------------

def start_drill(conn, player):
    fx_rows = get_fx_rows(conn)
    if not fx_rows:
        st.error("No FX data available, so there's nothing to build the drill from today.")
        return
    big_mac, _, _ = bigmac.get_item_prices({"name": "Big Mac", "source": "economist"})
    history = load_history(conn, player)
    st.session_state.questions = drill.make_questions(fx_rows, history, prices=big_mac)
    st.session_state.index = 0
    st.session_state.results = []
    st.session_state.feedback = None
    st.session_state.shown_at = time.monotonic()


def page_drill():
    st.header("🧮 Math Drill")
    conn = connect()
    state = st.session_state
    player = whose_scores()
    if player is None:
        return

    if "questions" not in state:
        st.write(f"{config.DRILL_QUESTIONS} timed questions built from today's real numbers. "
                 "Commas, $, %, k and m are all fine (e.g. 20k). Use a minus sign for losses or falls.")
        if st.button("▶️ Start today's drill", type="primary"):
            start_drill(conn, player)
            st.rerun()
        return

    questions, i = state.questions, state.index

    # How did the last answer go?
    if state.feedback:
        ok, message = state.feedback
        (st.success if ok else st.error)(md(message))

    if i < len(questions):
        q = questions[i]
        st.progress(i / len(questions), text=f"Question {i + 1} of {len(questions)}")
        with st.form(key=f"question-{len(state.results)}-{i}", clear_on_submit=True):
            st.markdown(f"### {md(q['question'])}")
            typed = st.text_input("Your answer", key=f"answer-{i}")
            submitted = st.form_submit_button("Submit (or press return)", type="primary")
        if submitted:
            seconds = time.monotonic() - state.shown_at
            given = drill.parse_answer(typed)
            correct = drill.is_correct(q["type"], given, q["answer"])
            result = dict(q, your_answer=typed.strip(), correct=correct, seconds=seconds)
            save_answer(conn, result, player)
            state.results.append(result)
            if correct:
                state.feedback = (True, f"✅ Correct ({drill.show_answer(q)}) in {seconds:.1f}s")
            else:
                state.feedback = (False, f"❌ The answer was {drill.show_answer(q)}. How: {q['how']}")
            state.index += 1
            state.shown_at = time.monotonic()
            st.rerun()
        if st.button("⏹ Stop the drill"):
            state.index = len(questions)
            st.rerun()
        return

    # Finished: the summary
    results = state.results
    if results:
        s = drill.summary(results, load_history(conn, player))
        cols = st.columns(4)
        cols[0].metric("Score", f"{s['score']}/{s['count']}")
        cols[1].metric("Average time", f"{s['avg_seconds']:.1f}s")
        cols[2].metric("Total time", f"{s['total_seconds']:.0f}s")
        if s["accuracy_7d"] is not None:
            cols[3].metric("7-day accuracy", f"{s['accuracy_7d']:.0%} {s['trend']}")
        if s["weakest"]:
            st.write(f"Weakest area: **{drill.NICE_NAMES[s['weakest']]}**. You'll see more of these next time.")
        with st.expander("Review your answers"):
            st.dataframe(pd.DataFrame([{
                "Question": r["question"], "You said": r["your_answer"], "Answer": drill.show_answer(r),
                "Right?": "✅" if r["correct"] else "❌", "Seconds": round(r["seconds"], 1),
            } for r in results]), hide_index=True, width="stretch")
    else:
        st.write("Drill stopped before any answers.")

    if st.button("🔁 Do another drill"):
        for key in ("questions", "index", "results", "feedback", "shown_at"):
            state.pop(key, None)
        st.rerun()


# ---------------------------------------------------------------------------
# Page 4: stats
# ---------------------------------------------------------------------------

def page_stats():
    st.header("📈 Drill Stats")
    player = whose_scores()
    if player is None:
        return
    history = load_history(connect(), player)
    if not history:
        st.write("No drill results yet. Do a drill first and your progress will show up here.")
        return

    speed = stats.speed_trend(history)
    streak = stats.streak(history)
    cols = st.columns(3)
    cols[0].metric("Streak", f"{streak} day{'s' if streak != 1 else ''}" + (" 🔥" if streak >= 3 else ""))
    cols[1].metric("Overall accuracy", f"{drill.accuracy(history):.0%}", help=f"Across {len(history)} questions")
    if speed["this_week"] is not None:
        delta = None
        if speed["last_week"] is not None:
            delta = f"{speed['this_week'] - speed['last_week']:+.1f}s vs last week"
        # Fewer seconds is better, so a negative change shows green
        cols[2].metric("Seconds per question (7 days)", f"{speed['this_week']:.1f}s", delta, delta_color="inverse")

    st.subheader("Accuracy by question type (weakest first)")
    by_type = pd.DataFrame([{
        "Question type": r["name"], "Accuracy (%)": round(r["accuracy"] * 100),
        "Answered": r["count"], "Avg seconds": round(r["avg_seconds"], 1),
    } for r in stats.by_type(history)])
    chart = alt.Chart(by_type).mark_bar(color=BLUE, cornerRadiusEnd=4, height=16).encode(
        x=alt.X("Accuracy (%):Q", scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("Question type:N", sort=None, title=None, axis=alt.Axis(labelLimit=200)),
        tooltip=["Question type", "Accuracy (%)", "Answered", "Avg seconds"],
    )
    labels = chart.mark_text(align="left", dx=4).encode(text=alt.Text("Accuracy (%):Q", format=".0f"))
    st.altair_chart((chart + labels).properties(height=alt.Step(28)))

    st.subheader("Score by day")
    days = pd.DataFrame([{
        "Date": d["date"], "Score (%)": round(d["right"] / d["count"] * 100), "Score": f"{d['right']}/{d['count']}",
    } for d in stats.by_day(history, last_n=30)])
    line = alt.Chart(days).mark_line(color=BLUE, strokeWidth=2, point=alt.OverlayMarkDef(size=64, filled=True)).encode(
        x=alt.X("yearmonthdate(Date):T", title=None, axis=alt.Axis(format="%b %d", tickCount="day")),
        y=alt.Y("Score (%):Q", scale=alt.Scale(domain=[0, 100])),
        tooltip=["Date", "Score", "Score (%)"],
    )
    st.altair_chart(line.properties(height=260))
    with st.expander("See the numbers"):
        st.dataframe(by_type, hide_index=True, width="stretch")
        st.dataframe(days, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Privacy page: open it with ?page=privacy
# ---------------------------------------------------------------------------

PRIVACY = """
# Privacy

EM Morning Desk is a free student project for practising emerging-market FX.

**What we collect.** When you create an account, we keep your email address and your password.
The password is stored securely (hashed) by our accounts provider, Supabase, so nobody can read it.
Your email is used only to sign you in and keep your drill scores separate from other people's.

**What we store.** Your drill answers, whether they were right, and how long they took.
The brief, rates and prices are the same for everyone and aren't linked to you.

**What we don't do.** We don't sell or share your information, show ads, or email you.

**Deleting your data.** To have your account and scores deleted, ask the site's owner.
"""


def page_privacy():
    st.markdown(PRIVACY)


# ---------------------------------------------------------------------------
# Navigation (left sidebar)
# ---------------------------------------------------------------------------

PAGES = {
    "📰 Brief": page_brief,
    "🌍 Prices": page_prices,
    "💵 USD vs EM": page_usd,
    "🗺️ Dollar in Trade": page_trade,
    "🧮 Drill": page_drill,
    "📈 Stats": page_stats,
}

if st.query_params.get("page") == "privacy":
    page_privacy()
    st.stop()

if not check_password() or not sign_in_page():
    st.stop()

st.sidebar.title("🌎 EM Morning Desk")
choice = st.sidebar.radio("Go to", list(PAGES), label_visibility="collapsed")
st.sidebar.caption("Work through the pages top to bottom: Brief → Prices → Drill.")
account_sidebar()
st.sidebar.markdown("[Privacy](?page=privacy)")
PAGES[choice]()
