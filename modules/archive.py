"""
modules/archive.py: saves each day's brief as a markdown file, e.g. briefs/2026-11-16.md,
so you can look back at past mornings. Open the files in any text editor (or VS Code,
which shows the formatting).

Running the brief again on the same day just rewrites that day's file.
"""

import os

from modules import brief

BRIEFS_DIR = "briefs"


def brief_markdown(day, summary, headlines, text, meetings=None, price_lines=None):
    """
    Build the markdown text for one day's brief (pure function, easy to test).
    meetings    = optional lines about upcoming central bank decisions
    price_lines = optional lines for "Prices around the world" (one per item)
    """
    lines = [f"# EM Morning Desk: {day}", ""]

    lines.append("## Top movers")
    for m in summary["top_movers"]:
        lines.append(f"- {brief.describe_move(m)}")
    lines.append("")

    lines.append("## Headlines")
    if headlines:
        for h in headlines:
            title = f"[{h['headline']}]({h['url']})" if h.get("url") else h["headline"]
            lines.append(f"- **{h['sentiment']}**: {title} ({h['source']})")
    else:
        lines.append("- No matching headlines today.")
    lines.append("")

    lines.append("## The brief")
    lines.append(text.strip())
    lines.append("")

    if meetings is not None:
        lines.append("## Central bank decisions, next 14 days")
        lines.extend(f"- {m}" for m in meetings)
        if not meetings:
            lines.append("- None scheduled.")
        lines.append("")

    if price_lines:
        lines.append("## Prices around the world")
        lines.extend(f"- {p}" for p in price_lines)
        lines.append("")

    lines.append("_Numbers calculated in Python; words written by Claude._")
    return "\n".join(lines) + "\n"


def save_brief_file(day, summary, headlines, text, folder=BRIEFS_DIR, meetings=None, price_lines=None):
    """Write briefs/<day>.md and return its path."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{day}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(brief_markdown(day, summary, headlines, text, meetings, price_lines))
    return path
