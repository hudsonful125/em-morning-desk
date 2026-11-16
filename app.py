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
import os
import time
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import config
import db
from data import bigmac, fx
from modules import brief, drill, prices, routine, stats

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
# Accounts: whose drill scores? (only matters on the shared website)
# ---------------------------------------------------------------------------

def sign_in_is_set_up():
    """True if the [auth] section (Google sign-in) is in Streamlit's Secrets. See the README."""
    try:
        return "auth" in st.secrets
    except Exception:  # no secrets file at all, e.g. on your Mac
        return False


def player_name():
    """
    Whose drill scores to show and save.
      - Google sign-in set up (online): each person signs in, and their email is their account.
      - Otherwise on the shared website (ADMIN_PASSWORD set): each person types a name.
      - On your Mac: "" (just you).
    Returns None if the person still needs to sign in or type a name.
    """
    if sign_in_is_set_up():
        if not st.user.get("is_logged_in", False):
            st.info("Sign in so your drill scores are saved to your own account. "
                    "We only see your name and email address.")
            if st.button("Sign in with Google", type="primary"):
                st.login()
            return None
        return (st.user.get("email") or "").lower()

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


def account_sidebar():
    """Shows who's signed in, with a Sign out button (only when Google sign-in is set up)."""
    if sign_in_is_set_up() and st.user.get("is_logged_in", False):
        st.sidebar.caption(f"Signed in as {st.user.email}")
        if st.sidebar.button("Sign out"):
            st.logout()


# ---------------------------------------------------------------------------
# Page 3: the drill
# ---------------------------------------------------------------------------

def start_drill(conn, player):
    fx_rows = get_fx_rows(conn)
    if not fx_rows:
        st.error("No FX data available, so there's nothing to build the drill from today.")
        return
    big_mac, _, _ = bigmac.get_item_prices({"name": "Big Mac", "source": "economist"})
    history = db.load_drill_results(conn, player=player)
    st.session_state.questions = drill.make_questions(fx_rows, history, prices=big_mac)
    st.session_state.index = 0
    st.session_state.results = []
    st.session_state.feedback = None
    st.session_state.shown_at = time.monotonic()


def page_drill():
    st.header("🧮 Math Drill")
    conn = connect()
    state = st.session_state
    player = player_name()
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
            db.save_drill_result(conn, TODAY, result, player=player)
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
        s = drill.summary(results, db.load_drill_results(conn, player=player))
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
    player = player_name()
    if player is None:
        return
    history = db.load_drill_results(connect(), player=player)
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
# Privacy page (Google sign-in needs a privacy policy link): open it with ?page=privacy
# ---------------------------------------------------------------------------

PRIVACY = """
# Privacy

EM Morning Desk is a free student project for practising emerging-market FX.

**What we collect.** If you sign in with Google, the app receives your name and email address.
Your email is used only to keep your drill answers and scores separate from other people's.
If you don't sign in, nothing about you is stored.

**What we store.** Your drill answers, whether they were right, and how long they took.
The brief, rates and prices are the same for everyone and aren't linked to you.

**What we don't do.** We don't sell or share your information, show ads, or email you.

**Deleting your data.** The app's database is reset from time to time. To have your scores
removed sooner, email the address shown on Google's sign-in screen.
"""


def page_privacy():
    st.markdown(PRIVACY)


# ---------------------------------------------------------------------------
# Navigation (left sidebar)
# ---------------------------------------------------------------------------

PAGES = {
    "📰 Brief": page_brief,
    "🌍 Prices": page_prices,
    "🧮 Drill": page_drill,
    "📈 Stats": page_stats,
}

if st.query_params.get("page") == "privacy":
    page_privacy()
    st.stop()

if not check_password():
    st.stop()

st.sidebar.title("🌎 EM Morning Desk")
choice = st.sidebar.radio("Go to", list(PAGES), label_visibility="collapsed")
st.sidebar.caption("Work through the pages top to bottom: Brief → Prices → Drill.")
account_sidebar()
st.sidebar.markdown("[Privacy](?page=privacy)")
PAGES[choice]()
