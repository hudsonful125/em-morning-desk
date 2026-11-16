"""
db.py: everything that reads or writes the SQLite database (desk.db).

SQLite is a database that lives in a single file on your computer.
No server or account needed; Python has it built in (the `sqlite3` module).
"""

import sqlite3

import config


def connect(db_path=None):
    """Open the database (creating the file and tables if needed) and return the connection."""
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us read columns by name, e.g. row["rate"]
    create_tables(conn)
    return conn


def create_tables(conn):
    """Create the tables if they don't exist yet. Safe to run every time."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fx_rates (
            date        TEXT NOT NULL,   -- e.g. '2026-11-12'
            pair        TEXT NOT NULL,   -- e.g. 'USD/BRL'
            rate        REAL NOT NULL,   -- latest rate
            prev_close  REAL NOT NULL,   -- previous day's closing rate
            pct_change  REAL NOT NULL,   -- % change from prev_close to rate
            PRIMARY KEY (date, pair)     -- one row per pair per day
        )
        """
    )
    # Phase 2: the day's raw news headlines (all of them, before filtering)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS news (
            date       TEXT NOT NULL,     -- the morning we fetched it, e.g. '2026-11-16'
            id         INTEGER NOT NULL,  -- Finnhub's id for the story
            category   TEXT,              -- 'general' or 'forex'
            headline   TEXT NOT NULL,
            source     TEXT,              -- e.g. 'Reuters'
            url        TEXT,
            published  INTEGER,           -- when it was published (Unix time)
            PRIMARY KEY (date, id)
        )
        """
    )
    # Phase 4: one row per drill question you answer
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS drill_results (
            date           TEXT NOT NULL,     -- e.g. '2026-11-16'
            question_type  TEXT NOT NULL,     -- e.g. 'pct_change'
            correct        INTEGER NOT NULL,  -- 1 = right, 0 = wrong
            seconds        REAL NOT NULL,     -- how long you took
            question       TEXT,              -- the question, so you can review it later
            your_answer    TEXT,
            right_answer   REAL
        )
        """
    )
    # Phase 2: the finished brief text, one per day, so re-running costs nothing
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS briefs (
            date  TEXT PRIMARY KEY,
            text  TEXT NOT NULL
        )
        """
    )
    conn.commit()


def save_fx_rates(conn, date, rows):
    """
    Save a list of FX rows for a given date.
    Each row is a dict with keys: pair, rate, prev_close, pct_change.
    If a row for that date + pair already exists, it is replaced.
    """
    for row in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO fx_rates (date, pair, rate, prev_close, pct_change)
            VALUES (?, ?, ?, ?, ?)
            """,
            (date, row["pair"], row["rate"], row["prev_close"], row["pct_change"]),
        )
    conn.commit()


def load_fx_rates(conn, date):
    """Return all FX rows saved for a given date, as a list of plain dicts."""
    cursor = conn.execute(
        "SELECT pair, rate, prev_close, pct_change FROM fx_rates WHERE date = ?",
        (date,),
    )
    return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Phase 2: news and briefs
# ---------------------------------------------------------------------------

def save_news(conn, date, items):
    """Save a list of news dicts (keys: id, category, headline, source, url, published)."""
    for item in items:
        conn.execute(
            """
            INSERT OR REPLACE INTO news (date, id, category, headline, source, url, published)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (date, item["id"], item["category"], item["headline"],
             item["source"], item["url"], item["published"]),
        )
    conn.commit()


def load_news(conn, date):
    """Return all headlines saved for a date, newest first."""
    cursor = conn.execute(
        """
        SELECT id, category, headline, source, url, published
        FROM news WHERE date = ? ORDER BY published DESC
        """,
        (date,),
    )
    return [dict(row) for row in cursor.fetchall()]


def save_brief(conn, date, text):
    """Save (or replace) the brief text for a date."""
    conn.execute("INSERT OR REPLACE INTO briefs (date, text) VALUES (?, ?)", (date, text))
    conn.commit()


def load_brief(conn, date):
    """Return the saved brief text for a date, or None if there isn't one."""
    row = conn.execute("SELECT text FROM briefs WHERE date = ?", (date,)).fetchone()
    return row["text"] if row else None


# ---------------------------------------------------------------------------
# Phase 4: drill results
# ---------------------------------------------------------------------------

def save_drill_result(conn, date, result):
    """Save one answered question. `result` is a dict from modules/drill.py."""
    conn.execute(
        """
        INSERT INTO drill_results (date, question_type, correct, seconds, question, your_answer, right_answer)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (date, result["type"], int(result["correct"]), result["seconds"],
         result["question"], result["your_answer"], result["answer"]),
    )
    conn.commit()


def load_drill_results(conn, since_date=None):
    """Return drill rows (oldest first), optionally only from `since_date` onward."""
    if since_date:
        cursor = conn.execute(
            "SELECT * FROM drill_results WHERE date >= ? ORDER BY rowid", (since_date,)
        )
    else:
        cursor = conn.execute("SELECT * FROM drill_results ORDER BY rowid")
    return [dict(row) for row in cursor.fetchall()]
