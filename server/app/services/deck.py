from __future__ import annotations

import json
import random
import sqlite3
from datetime import date
from typing import Any

from app.config import Settings


def collect_word(conn: sqlite3.Connection, settings: Settings, word: str, sentence: str, source_url: str | None) -> int:
    normalized = word.strip().lower()
    existing = conn.execute("SELECT word FROM words WHERE word = ?", (normalized,)).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE words
            SET remaining = ?, status = 'active', updated_at = CURRENT_TIMESTAMP
            WHERE word = ?
            """,
            (settings.graduate_after, normalized),
        )
    else:
        conn.execute(
            """
            INSERT INTO words (word, definitions, remaining, status)
            VALUES (?, ?, ?, 'pending')
            """,
            (normalized, "[]", settings.graduate_after),
        )

    cursor = conn.execute(
        """
        INSERT INTO sentences (word, sentence, source_url, enriched)
        VALUES (?, ?, ?, 0)
        """,
        (normalized, sentence.strip(), source_url),
    )
    conn.commit()
    return int(cursor.lastrowid)


def get_or_create_daily_deck(conn: sqlite3.Connection, settings: Settings, day: date) -> list[dict[str, Any]]:
    day_key = day.isoformat()
    existing = _load_daily_deck(conn, day_key)
    if existing:
        return existing

    return rebuild_daily_deck(conn, settings, day)


def rebuild_daily_deck(conn: sqlite3.Connection, settings: Settings, day: date) -> list[dict[str, Any]]:
    day_key = day.isoformat()
    conn.execute("DELETE FROM daily_deck WHERE date = ?", (day_key,))

    review_cards = _select_review_cards(conn, settings.daily_review_words)
    selected_words = {row["word"] for row in review_cards}
    new_cards = _select_new_cards(conn, settings.daily_new_words, selected_words)

    for row in review_cards:
        conn.execute(
            "INSERT INTO daily_deck (date, word, sentence_id, is_new) VALUES (?, ?, ?, 0)",
            (day_key, row["word"], row["sentence_id"]),
        )
    for row in new_cards:
        conn.execute(
            "UPDATE words SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE word = ?",
            (row["word"],),
        )
        conn.execute(
            "INSERT INTO daily_deck (date, word, sentence_id, is_new) VALUES (?, ?, ?, 1)",
            (day_key, row["word"], row["sentence_id"]),
        )
    conn.commit()
    return _load_daily_deck(conn, day_key)


def answer_card(conn: sqlite3.Connection, day: date, word: str, correct: bool) -> dict[str, Any]:
    normalized = word.strip().lower()
    day_key = day.isoformat()
    deck_row = conn.execute(
        "SELECT * FROM daily_deck WHERE date = ? AND word = ?",
        (day_key, normalized),
    ).fetchone()
    if not deck_row:
        raise ValueError("word is not in today's deck")
    if deck_row["answered"]:
        return {"word": normalized, "already_answered": True}

    conn.execute(
        "UPDATE daily_deck SET answered = 1, correct = ? WHERE date = ? AND word = ?",
        (1 if correct else 0, day_key, normalized),
    )
    conn.execute(
        "INSERT INTO reviews (word, sentence_id, correct) VALUES (?, ?, ?)",
        (normalized, deck_row["sentence_id"], 1 if correct else 0),
    )
    if correct:
        conn.execute(
            """
            UPDATE words
            SET remaining = MAX(remaining - 1, 0),
                status = CASE WHEN MAX(remaining - 1, 0) = 0 THEN 'graduated' ELSE status END,
                updated_at = CURRENT_TIMESTAMP
            WHERE word = ?
            """,
            (normalized,),
        )
    conn.commit()
    row = conn.execute("SELECT remaining, status FROM words WHERE word = ?", (normalized,)).fetchone()
    return {"word": normalized, "already_answered": False, "remaining": row["remaining"], "status": row["status"]}


def backlog_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM words WHERE status = 'active'").fetchone()
    return int(row["count"])


def pending_enrichment_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM sentences WHERE enriched = 0").fetchone()
    return int(row["count"])


def _select_review_cards(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        WITH latest_sentence AS (
            SELECT s.word, s.id AS sentence_id,
                   ROW_NUMBER() OVER (PARTITION BY s.word ORDER BY s.created_at DESC, s.id DESC) AS rn
            FROM sentences s
            WHERE s.enriched = 1
        ),
        last_review AS (
            SELECT word, MAX(answered_at) AS last_answered_at
            FROM reviews
            GROUP BY word
        )
        SELECT w.word, latest_sentence.sentence_id
        FROM words w
        JOIN latest_sentence ON latest_sentence.word = w.word AND latest_sentence.rn = 1
        LEFT JOIN last_review ON last_review.word = w.word
        WHERE w.status = 'active' AND w.remaining > 0
        ORDER BY last_review.last_answered_at IS NOT NULL, last_review.last_answered_at ASC, w.updated_at ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def _select_new_cards(conn: sqlite3.Connection, limit: int, excluded_words: set[str]) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        WITH latest_sentence AS (
            SELECT s.word, s.id AS sentence_id,
                   ROW_NUMBER() OVER (PARTITION BY s.word ORDER BY s.created_at DESC, s.id DESC) AS rn
            FROM sentences s
            WHERE s.enriched = 1
        )
        SELECT w.word, latest_sentence.sentence_id
        FROM words w
        JOIN latest_sentence ON latest_sentence.word = w.word AND latest_sentence.rn = 1
        WHERE w.status = 'pending'
        ORDER BY w.created_at ASC
        """,
    ).fetchall()
    available = [row for row in rows if row["word"] not in excluded_words]
    return available[:limit]


def _load_daily_deck(conn: sqlite3.Connection, day_key: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT d.date, d.word, d.sentence_id, d.is_new, d.answered, d.correct,
               w.part_of_speech, w.definitions, w.phonetic, w.audio_url, w.remaining, w.status,
               s.sentence, s.answer_zh, s.distractors, s.trans_zh
        FROM daily_deck d
        JOIN words w ON w.word = d.word
        JOIN sentences s ON s.id = d.sentence_id
        WHERE d.date = ?
        ORDER BY d.is_new ASC, d.word ASC
        """,
        (day_key,),
    ).fetchall()
    cards = [_card_from_row(row) for row in rows]
    rng = random.Random(day_key)
    for card in cards:
        options = [card["answer_zh"], *card["distractors"]]
        rng.shuffle(options)
        card["options"] = options
    return cards


def _card_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "word": row["word"],
        "sentence_id": row["sentence_id"],
        "sentence": row["sentence"],
        "is_new": bool(row["is_new"]),
        "answered": bool(row["answered"]),
        "correct": None if row["correct"] is None else bool(row["correct"]),
        "part_of_speech": row["part_of_speech"],
        "definitions": json.loads(row["definitions"] or "[]"),
        "phonetic": row["phonetic"],
        "audio_url": row["audio_url"],
        "remaining": row["remaining"],
        "status": row["status"],
        "answer_zh": row["answer_zh"],
        "distractors": json.loads(row["distractors"] or "[]"),
        "trans_zh": row["trans_zh"],
    }
