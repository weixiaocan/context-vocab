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
    conn.commit()
