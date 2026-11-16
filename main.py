"""
main.py: the entry point. Run it from the terminal inside the em-morning-desk folder.

    python3 main.py --fx              show today's EM currency moves
    python3 main.py --brief           the morning brief: moves, headlines, and Claude's note
    python3 main.py --brief --refresh fetch everything fresh and rewrite the brief
    python3 main.py --prices          Big Mac (and other items) priced in USD at today's rates
    python3 main.py --drill           timed mental-math drill built from today's numbers
    python3 main.py --stats           your drill history: accuracy by type, speed, streak
    python3 main.py                   the full morning routine: Brief -> Prices -> Drill
"""

import argparse
import os
from datetime import date

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.table import Table

import config
import db
from data import bigmac, fx, news
from modules import brief, drill, prices, routine, stats

console = Console()


def warn(messages):
    """Print each warning in yellow."""
    for message in messages:
        console.print(f"[yellow]⚠ {message}[/yellow]")


def get_fx(conn, today, refresh):
    """Fetch (or load) today's rates, print any warnings, and return the rows."""
    rows, warnings = fx.get_fx_rates(conn, today, os.getenv("TWELVE_DATA_KEY"), refresh=refresh)
    warn(warnings)
    return rows


def print_fx_table(rows, today):
    """Print the FX rows as a table, biggest mover first."""
    names = {c["pair"]: c for c in config.CURRENCIES}

    table = Table(title=f"EM FX: overnight moves vs USD ({today})")
    table.add_column("Pair")
    table.add_column("Country")
    table.add_column("Prev close", justify="right")
    table.add_column("Latest", justify="right")
    table.add_column("% change", justify="right")
    table.add_column("Local currency")

    for row in rows:
        pct = row["pct_change"]
        # Green when the local currency strengthened (USD/XXX fell), red when it weakened.
        color = "green" if pct < 0 else "red" if pct > 0 else "white"
        info = names.get(row["pair"], {})
        table.add_row(
            row["pair"],
            info.get("country", ""),
            f"{row['prev_close']:,.4f}",
            f"{row['rate']:,.4f}",
            f"[{color}]{pct:+.2f}%[/{color}]",
            f"[{color}]{info.get('currency', '')} {fx.direction_word(pct)}[/{color}]",
        )

    console.print(table)
    console.print("[dim]USD/XXX up = the local currency weakened (a dollar buys more of it).[/dim]")


def show_fx(conn, refresh):
    """--fx: just the currency table."""
    today = date.today().isoformat()
    rows = get_fx(conn, today, refresh)
    if not rows:
        console.print("[red]No FX data available for today. Check your API key and internet connection.[/red]")
        return
    print_fx_table(rows, today)


def show_brief(conn, refresh):
    """--brief: the numbers (Python), the headlines (Finnhub), and the note (Claude)."""
    console.rule(f"[bold]EM MORNING DESK: {date.today():%a %b %d}[/bold]")
    with console.status("Getting today's rates, headlines and brief (the first run of the day takes about a minute)..."):
        r = routine.make_brief(conn, refresh=refresh)
    warn(r["warnings"])
    if not r["fx_rows"]:
        console.print(f"[red]{r['error']}[/red]")
        return

    # Print the key numbers first, so you see the facts before the commentary
    console.print("\n[bold]📊 Top movers[/bold]")
    for m in r["summary"]["top_movers"]:
        color = "red" if m["direction"] == "weakened" else "green"
        console.print(f"  [{color}]{brief.describe_move(m)}[/{color}]")

    console.print("\n[bold]📰 Headlines[/bold]")
    if r["headlines"]:
        mood_color = {"positive": "green", "negative": "red", "neutral": "dim"}
        for h in r["headlines"]:
            c = mood_color[h["sentiment"]]
            console.print(f"  [{c}]{h['sentiment'][:3].upper()}[/{c}]  {h['headline']} [dim]({h['source']})[/dim]")
    else:
        console.print("  [dim]No matching headlines today.[/dim]")

    console.print("\n[bold]🏦 Central bank decisions, next 14 days[/bold]")
    for line in r["meetings"] or ["None scheduled in data/central_bank_calendar.csv."]:
        console.print(f"  {escape(line)}")

    if r["error"]:
        warn([r["error"]])
        return
    console.print("\n[bold]📝 The Brief[/bold]")
    console.print(Markdown(r["text"]))
    console.print("\n[dim]Numbers calculated in Python; words written by Claude.[/dim]")
    console.print(f"[dim]Saved to briefs/{date.today().isoformat()}.md[/dim]")


def show_prices(conn, refresh):
    """--prices: each item from config.ITEMS, priced in USD at today's rates."""
    today = date.today().isoformat()
    fx_rows = get_fx(conn, today, refresh)
    if not fx_rows:
        console.print("[red]No FX data available, so prices can't be converted today.[/red]")
        return

    for item in config.ITEMS:
        name = item["name"]
        local_prices, price_date, warnings = bigmac.get_item_prices(item)
        warn(warnings)
        table_rows = prices.build_price_table(fx_rows, local_prices)
        if not table_rows:
            continue

        us_price = local_prices["USD"]
        table = Table(title=f"🌍 PRICES AROUND THE WORLD: {name} at today's rates ({today})")
        table.add_column("Country")
        table.add_column("Local price", justify="right")
        table.add_column("Today's rate", justify="right")
        table.add_column("Price in USD", justify="right")
        table.add_column("vs US", justify="right")
        table.add_column("Implied PPP rate", justify="right")

        for r in table_rows:
            v = r["valuation_pct"]
            color = "green" if v < 0 else "red"
            label = "under" if v < 0 else "over"
            table.add_row(
                r["country"],
                f"{r['local_price']:,.2f} {r['code']}",
                f"{r['rate']:,.2f}",
                f"${r['usd_price']:.2f}",
                f"[{color}]{v:+.0f}% {label}[/{color}]",
                f"{r['implied_ppp']:,.2f}",
            )

        console.print(table)
        console.print(f"US price: ${us_price:.2f}. Sorted from most undervalued to most overvalued.")
        console.print(f"[bold]→ {prices.news_tie_in(table_rows, name, item.get('phrase'))}[/bold]")
        if item.get("note"):
            console.print(f"[dim]{item['note']}[/dim]")
        console.print(f"[dim]Implied PPP rate = the USD/XXX rate that would make a {name} cost the same as in the US.\n"
                      f"{name} prices are from {price_date or 'unknown date'}"
                      + (" (The Economist updates them twice a year)" if item["source"] == "economist" else "")
                      + "; exchange rates are today's.[/dim]\n")


def show_drill(conn, refresh):
    """--drill: an interactive, timed quiz built from today's numbers. Results are saved."""
    today = date.today().isoformat()
    fx_rows = get_fx(conn, today, refresh)
    if not fx_rows:
        console.print("[red]No FX data available, so there's nothing to build the drill from today.[/red]")
        return

    # Big Mac prices make the conversion questions concrete (optional)
    big_mac, _, _ = bigmac.get_item_prices({"name": "Big Mac", "source": "economist"})

    history = db.load_drill_results(conn)
    questions = drill.make_questions(fx_rows, history, prices=big_mac)

    console.rule(f"[bold]🧮 MATH DRILL ({len(questions)} questions)[/bold]")
    console.print("[dim]Type a number and press return. Commas, $, %, k and m are fine (e.g. 20k). "
                  "Use a minus sign for losses or falls. Type q to stop.[/dim]\n")

    results = drill.run_drill(questions, ask=console.input, say=console.print)
    if not results:
        return
    for r in results:
        db.save_drill_result(conn, today, r)

    s = drill.summary(results, db.load_drill_results(conn))
    console.print()
    line = f"[bold]Score: {s['score']}/{s['count']}[/bold] · Avg {s['avg_seconds']:.1f}s · Total {s['total_seconds']:.0f}s"
    if s["accuracy_7d"] is not None:
        line += f" · 7-day accuracy: {s['accuracy_7d']:.0%} {s['trend']}"
    console.print(line)
    if s["weakest"]:
        console.print(f"Weakest area: {drill.NICE_NAMES[s['weakest']]}. You'll see more of these next time.")


def show_stats(conn):
    """--stats: how your drill practice is going."""
    history = db.load_drill_results(conn)
    if not history:
        console.print("No drill results yet. Run [bold]python3 main.py --drill[/bold] first.")
        return

    console.rule("[bold]📈 DRILL STATS[/bold]")

    table = Table(title="Accuracy by question type (weakest first)")
    table.add_column("Question type")
    table.add_column("Answered", justify="right")
    table.add_column("Accuracy", justify="right")
    table.add_column("Avg time", justify="right")
    for r in stats.by_type(history):
        color = "green" if r["accuracy"] >= 0.8 else "yellow" if r["accuracy"] >= 0.5 else "red"
        table.add_row(r["name"], str(r["count"]),
                      f"[{color}]{r['accuracy']:.0%}[/{color}]", f"{r['avg_seconds']:.1f}s")
    console.print(table)

    days = Table(title="Recent days")
    days.add_column("Date")
    days.add_column("Score", justify="right")
    for d in stats.by_day(history):
        days.add_row(d["date"], f"{d['right']}/{d['count']}")
    console.print(days)

    speed = stats.speed_trend(history)
    if speed["this_week"] is not None:
        line = f"Speed: {speed['this_week']:.1f}s per question this week"
        if speed["last_week"] is not None:
            line += f" vs {speed['last_week']:.1f}s last week {speed['arrow']}"
        console.print(line)
    n = stats.streak(history)
    console.print(f"Streak: {n} day{'s' if n != 1 else ''} in a row" + (" 🔥" if n >= 3 else ""))
    console.print(f"Overall accuracy: {drill.accuracy(history):.0%} across {len(history)} questions")


def run_routine(conn, refresh):
    """No flags: the full morning routine, Brief -> Prices -> Drill."""
    show_brief(conn, refresh)
    console.print()
    show_prices(conn, refresh=False)  # rates were already fetched by the brief

    answer = console.input("[bold]Press return to start the drill, or type s and press return to skip: [/bold]")
    if answer.strip().lower().startswith("s"):
        console.print("Drill skipped. See you tomorrow.")
        return
    show_drill(conn, refresh=False)


def main():
    load_dotenv()  # reads your API keys from the .env file into the environment

    parser = argparse.ArgumentParser(description="EM Morning Desk")
    parser.add_argument("--fx", action="store_true", help="show today's EM currency moves")
    parser.add_argument("--brief", action="store_true", help="show the morning brief")
    parser.add_argument("--prices", action="store_true", help="show Prices Around the World")
    parser.add_argument("--drill", action="store_true", help="run the timed math drill")
    parser.add_argument("--stats", action="store_true", help="show your drill history")
    parser.add_argument("--refresh", action="store_true", help="re-fetch today's data instead of using the saved copy")
    args = parser.parse_args()

    conn = db.connect()

    if args.brief:
        show_brief(conn, args.refresh)
    elif args.prices:
        show_prices(conn, args.refresh)
    elif args.drill:
        show_drill(conn, args.refresh)
    elif args.stats:
        show_stats(conn)
    elif args.fx:
        show_fx(conn, args.refresh)
    else:
        run_routine(conn, args.refresh)

    conn.close()


if __name__ == "__main__":
    main()
