"""Tests for separate drill scores per person on the shared website."""

import sqlite3

import db

RESULT = {"type": "pct_change", "correct": True, "seconds": 3.0,
          "question": "Q?", "your_answer": "1", "answer": 1.0}


def test_each_player_sees_only_their_own_results(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    db.save_drill_result(conn, "2026-11-16", RESULT)                    # you, on the Mac
    db.save_drill_result(conn, "2026-11-16", RESULT, player="maya")
    db.save_drill_result(conn, "2026-11-17", RESULT, player="maya")
    assert len(db.load_drill_results(conn)) == 1
    assert len(db.load_drill_results(conn, player="maya")) == 2
    assert len(db.load_drill_results(conn, since_date="2026-11-17", player="maya")) == 1
    assert db.load_drill_results(conn, player="sam") == []


def test_old_database_gets_player_column(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.execute("""CREATE TABLE drill_results (date TEXT NOT NULL, question_type TEXT NOT NULL,
                   correct INTEGER NOT NULL, seconds REAL NOT NULL, question TEXT,
                   your_answer TEXT, right_answer REAL)""")
    old.execute("INSERT INTO drill_results VALUES ('2026-11-15', 'bps', 1, 2.0, 'Q', '5', 5)")
    old.commit()
    old.close()
    conn = db.connect(path)  # adds the column; old rows count as yours
    assert len(db.load_drill_results(conn)) == 1
    db.save_drill_result(conn, "2026-11-16", RESULT, player="maya")
    assert len(db.load_drill_results(conn, player="maya")) == 1
