from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if path.parent and str(path.parent) not in {"", "."}:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS words (
            word TEXT PRIMARY KEY,
            part_of_speech TEXT,
            definitions TEXT,
            phonetic TEXT,
            audio_url TEXT,
            remaining INTEGER NOT NULL,
            review_interval INTEGER NOT NULL DEFAULT 0,
            due_date TEXT,
            status TEXT NOT NULL CHECK (status IN ('pending', 'active', 'graduated')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL REFERENCES words(word) ON DELETE CASCADE,
            sentence TEXT NOT NULL,
            source_url TEXT,
            answer_zh TEXT,
            definition_zh TEXT,
            distractors TEXT,
            trans_zh TEXT,
            enriched INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS daily_deck (
            date TEXT NOT NULL,
            word TEXT NOT NULL REFERENCES words(word) ON DELETE CASCADE,
            sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
            is_new INTEGER NOT NULL,
            answered INTEGER NOT NULL DEFAULT 0,
            correct INTEGER,
            PRIMARY KEY (date, word)
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL REFERENCES words(word) ON DELETE CASCADE,
            sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
            correct INTEGER NOT NULL,
            answered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_sentences_word_created
            ON sentences(word, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_sentences_enriched
            ON sentences(enriched);
        CREATE INDEX IF NOT EXISTS idx_reviews_word_answered
            ON reviews(word, answered_at);
        """
    )
    _add_column_if_missing(conn, "words", "review_interval", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "words", "due_date", "TEXT")
    _add_column_if_missing(conn, "sentences", "definition_zh", "TEXT")
    conn.execute(
        """
        UPDATE sentences
        SET enriched = 0
        WHERE enriched = 1
          AND (definition_zh IS NULL OR TRIM(definition_zh) = '')
        """
    )
    conn.commit()


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
