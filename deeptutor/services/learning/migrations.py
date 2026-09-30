"""Atomic, repeatable upgrade of the former Mathematics-only SQLite schema."""

import sqlite3
from pathlib import Path


def migrate_subjects(db_path: Path) -> None:
    # Foreign-key checks are disabled only on this private migration connection.
    # Existing IDs survive table rebuilds; check all references before commit.
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN IMMEDIATE")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(learning_topic_scores)")}
        if "subject" in columns:
            conn.commit()
            return
        conn.execute("""CREATE TABLE learning_sessions_new (
            id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, chat_session_id TEXT NOT NULL,
            subject TEXT NOT NULL DEFAULT 'Mathematics', stage TEXT NOT NULL DEFAULT 'needs_diagnostic',
            budget_minutes INTEGER NOT NULL DEFAULT 15, created_at REAL NOT NULL, updated_at REAL NOT NULL,
            UNIQUE(owner_user_id, chat_session_id, subject))""")
        conn.execute("INSERT INTO learning_sessions_new SELECT * FROM learning_sessions")
        conn.execute("DROP TABLE learning_sessions")
        conn.execute("ALTER TABLE learning_sessions_new RENAME TO learning_sessions")
        conn.execute("""CREATE TABLE learning_topic_scores_new (
            owner_user_id TEXT NOT NULL, subject TEXT NOT NULL DEFAULT 'Mathematics',
            topic_id TEXT NOT NULL, topic_name TEXT NOT NULL, correct INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 0, last_percentage REAL NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL, PRIMARY KEY(owner_user_id, subject, topic_id))""")
        conn.execute("""INSERT INTO learning_topic_scores_new
            SELECT owner_user_id, 'Mathematics', topic_id, topic_name, correct, total,
                   last_percentage, updated_at FROM learning_topic_scores""")
        conn.execute("DROP TABLE learning_topic_scores")
        conn.execute("ALTER TABLE learning_topic_scores_new RENAME TO learning_topic_scores")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise sqlite3.IntegrityError("Learning migration found invalid foreign-key references.")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
