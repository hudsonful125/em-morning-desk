"""
modules/brief.py: builds the morning brief.

How the work is split (the project's main rule):
  1. PYTHON does every number: top movers, which currencies got stronger or weaker,
     the average move, and the headline mood count. (build_summary)
  2. Python turns that into a short plain-text fact sheet. (summary_to_text)
  3. CLAUDE only turns the fact sheet + headlines into readable sentences,
     and is told never to invent a number. (write_brief)

The finished brief is saved in the database, so running --brief again the same
morning shows it instantly and costs nothing.
"""

import anthropic

import config

SYSTEM_PROMPT = """You are a sell-side emerging-markets FX strategist writing a short morning note \
for a college finance student who is training to work on an EM sales & trading desk.

Rules:
- Use ONLY the numbers in the fact sheet. Never invent or estimate a rate, percentage, \
date, or other figure. Copy numbers exactly as given (you may round to 1 decimal place).
- The fact sheet already says whether each currency strengthened or weakened. Trust it. \
Do not re-derive direction from the USD/XXX quote.
- Only link a move to a cause if a listed headline supports it. Otherwise say the move \
happened without claiming why, or say "possibly" and name the headline you are leaning on.
- Plain, confident desk language. No hype, no investment advice.

Write exactly these three sections in Markdown:

## Overnight summary
3 to 5 sentences in the style of a sell-side morning note.

## What to watch today
One line. If the fact sheet lists upcoming central bank rate decisions, name the nearest \
one or two (with the date as given) when they matter for today's movers.

## Talking points
Three numbered points the student could use in an interview or class. Each should \
connect a move or headline to a bigger idea (e.g. rate differentials, oil and \
commodity exporters, the US dollar, carry trades), explained simply."""


# ---------------------------------------------------------------------------
# Step 1: all the math, in Python
# ---------------------------------------------------------------------------

def build_summary(fx_rows, headlines):
    """
    Turn today's FX rows and headlines into a dict of facts.
    fx_rows: dicts with pair, rate, prev_close, pct_change (from data/fx.py)
    headlines: dicts with headline, source, sentiment (from data/news.py)
    """
    names = {c["pair"]: c for c in config.CURRENCIES}

    moves = []
    for row in fx_rows:
        info = names.get(row["pair"], {})
        pct = row["pct_change"]
        moves.append({
            "pair": row["pair"],
            "code": row["pair"].split("/")[1],                 # "USD/BRL" -> "BRL"
            "country": info.get("country", ""),
            "currency": info.get("currency", ""),
            "prev_close": row["prev_close"],
            "rate": row["rate"],
            "pct_change": pct,
            # USD/XXX up means a dollar buys MORE local currency -> local currency weakened
            "direction": "weakened" if pct > 0 else "strengthened" if pct < 0 else "unchanged",
        })

    # Sort by size of move, biggest first
    moves.sort(key=lambda m: abs(m["pct_change"]), reverse=True)

    # Count headline moods
    mood = {"positive": 0, "negative": 0, "neutral": 0}
    for h in headlines:
        mood[h["sentiment"]] += 1
    if mood["positive"] > mood["negative"]:
        overall_mood = "positive"
    elif mood["negative"] > mood["positive"]:
        overall_mood = "negative"
    else:
        overall_mood = "mixed/neutral"

    average_move = sum(m["pct_change"] for m in moves) / len(moves) if moves else 0.0

    return {
        "moves": moves,
        "top_movers": moves[:3],
        "strengthened": [m for m in moves if m["direction"] == "strengthened"],
        "weakened": [m for m in moves if m["direction"] == "weakened"],
        # Average USD/XXX % change: positive = EM currencies weaker on average
        "average_move": average_move,
        "mood_counts": mood,
        "overall_mood": overall_mood,
    }


def describe_move(m):
    """One line of plain English for a currency move, with numbers already rounded."""
    return (f"{m['country']} {m['currency']} ({m['code']}) {m['direction']} "
            f"{abs(m['pct_change']):.2f}% vs USD ({m['pair']} {m['prev_close']:,.4f} -> {m['rate']:,.4f})")


def summary_to_text(summary, headlines, meetings=None):
    """
    Turn the summary dict + headlines into the plain-text fact sheet Claude reads.
    `meetings` = optional list of lines about upcoming central bank decisions.
    """
    lines = ["FACT SHEET (all numbers calculated in Python; use only these)", ""]

    lines.append("Top 3 movers:")
    for m in summary["top_movers"]:
        lines.append(f"- {describe_move(m)}")

    lines.append("")
    lines.append(f"Strengthened vs USD ({len(summary['strengthened'])}): "
                 + (", ".join(f"{m['code']} {abs(m['pct_change']):.2f}%" for m in summary["strengthened"]) or "none"))
    lines.append(f"Weakened vs USD ({len(summary['weakened'])}): "
                 + (", ".join(f"{m['code']} {abs(m['pct_change']):.2f}%" for m in summary["weakened"]) or "none"))

    avg = summary["average_move"]
    lines.append(f"Average move across tracked EM currencies: {abs(avg):.2f}% "
                 + ("weaker" if avg > 0 else "stronger" if avg < 0 else "unchanged") + " vs USD")

    counts = summary["mood_counts"]
    lines.append("")
    lines.append(f"Headline mood (simple keyword score): {counts['positive']} positive, "
                 f"{counts['negative']} negative, {counts['neutral']} neutral -> overall {summary['overall_mood']}")

    lines.append("")
    lines.append("Relevant headlines (newest first):")
    if headlines:
        for h in headlines:
            lines.append(f"- [{h['sentiment']}] {h['headline']} ({h['source']})")
    else:
        lines.append("- (no headlines available today)")

    if meetings is not None:
        lines.append("")
        lines.append("Central bank rate decisions in the next 14 days:")
        if meetings:
            for m in meetings:
                lines.append(f"- {m}")
        else:
            lines.append("- none scheduled")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 3: the words, from Claude
# ---------------------------------------------------------------------------

def write_brief(fact_sheet, api_key, client=None):
    """
    Send the fact sheet to Claude and return (brief_text, error_message).
    Exactly one of the two is None.
    `client` can be passed in by tests so no real API call is made.
    """
    if client is None:
        if not api_key:
            return None, "No ANTHROPIC_API_KEY found in your .env file, so Claude couldn't write the brief."
        client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.beta.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            output_config={"effort": config.CLAUDE_EFFORT},
            # If the main model declines for safety reasons, Anthropic retries on a
            # suitable fallback model inside the same call ("server-side fallback").
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": fact_sheet}],
        )
    except anthropic.AuthenticationError:
        return None, "Anthropic rejected the API key. Check ANTHROPIC_API_KEY in your .env file."
    except anthropic.RateLimitError:
        return None, "Anthropic says you're sending requests too fast. Wait a minute and try again."
    except anthropic.APIStatusError as error:
        if error.status_code == 400 and "credit" in str(error).lower():
            return None, "Your Anthropic account is out of credit. Add some under Billing at console.anthropic.com."
        return None, f"Anthropic API error ({error.status_code}): {error.message}"
    except anthropic.APIConnectionError:
        return None, "Couldn't reach the Anthropic API. Check your internet connection."

    if response.stop_reason == "refusal":
        return None, "Claude declined to write today's brief. Try again with --refresh."

    # The reply is a list of blocks; we only want the text ones.
    text = "\n".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        return None, "Claude returned an empty brief. Try again with --refresh."
    return text, None
