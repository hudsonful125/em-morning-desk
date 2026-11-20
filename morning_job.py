"""
morning_job.py: the hands-off version of the brief, for the weekday-morning schedule.

It does the same work as `python3 main.py --brief`, but without needing you there:
  0. updates the central bank rates in data/policy_rates.csv from BIS (data/rate_updater.py)
  1. gets today's rates, headlines and Claude's brief (and saves briefs/YYYY-MM-DD.md)
  2. emails the brief to you, if email is set up in .env (see modules/emailer.py)
  3. pops up a Mac notification saying it's ready

Run it by hand to test it:   python3 morning_job.py
The schedule is set up with:  bash schedule/install_mac.sh   (see the README)
What happened each morning is written to ~/Library/Logs/em-morning-desk.log.
"""

import os
import shutil
import subprocess
from datetime import date, datetime

# The schedule starts this script from your home folder, so first move into the project
# folder: that's where .env, desk.db and the other files live.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv  # noqa: E402  (imports after chdir on purpose)

import db  # noqa: E402
from data import rate_updater  # noqa: E402
from modules import archive, emailer, routine  # noqa: E402


def log(message):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def notify(title, message):
    """A Mac notification in the top-right corner (does nothing on other computers)."""
    if shutil.which("osascript"):
        safe = message.replace('"', "'")
        subprocess.run(["osascript", "-e", f'display notification "{safe}" with title "{title}"'], check=False)


def main():
    load_dotenv()
    today = date.today()
    log("Starting the morning brief")

    rate_changes, rate_warnings = rate_updater.update_rates_file()
    for line in rate_changes:
        log(f"Policy rate updated: {line}")
    for w in rate_warnings:
        log(f"Warning: {w}")

    conn = db.connect()
    r = routine.make_brief(conn, today)
    conn.close()
    for w in r["warnings"]:
        log(f"Warning: {w}")
    if r["error"]:
        log(f"Error: {r['error']}")
        notify("EM Morning Desk", f"No brief today: {r['error']}")
        return

    log(f"Brief saved to briefs/{today.isoformat()}.md")
    body = archive.brief_markdown(today.isoformat(), r["summary"], r["headlines"], r["text"],
                                  r["meetings"], routine.price_lines(r["fx_rows"]))
    if rate_changes:  # a central bank moved and the rates file updated itself
        body += "\n\n## 🏦 Policy rates updated\n\n" + "\n".join(f"- {c}" for c in rate_changes) + "\n"
    reminders = routine.rate_reminders(today)
    if reminders:  # a central bank has met, so the rates file may need updating
        body += "\n\n## ⏰ Reminder\n\n" + "\n".join(f"- {m}" for m in reminders) + "\n"
    error = emailer.send_email(f"EM Morning Desk: {today:%a %b %d}", body)
    if error:
        log(error)
        notify("EM Morning Desk", "Your brief is ready in the briefs folder.")
    else:
        log("Brief emailed")
        notify("EM Morning Desk", "Your brief is in your inbox.")


if __name__ == "__main__":
    main()
