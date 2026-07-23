from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from typing import Any

from app.config import Settings
from app.models import DictEntry


def collect_word(
    conn: sqlite3.Connection,
    settings: Settings,
    word: str,
    sentence: str,
    source_url: str | None,
    dictionary_entry: DictEntry | None = None,
) -> int:
    normalized = word.strip().lower()
    normalized_sentence = sentence.strip()
    today_key = date.today().isoformat()
    duplicate = conn.execute(
        "SELECT id FROM sentences WHERE word = ? AND sentence = ? ORDER BY id LIMIT 1",
        (normalized, normalized_sentence),
    ).fetchone()
    if duplicate:
        _save_dictionary_entry(conn, normalized, dictionary_entry)
        conn.commit()
        return int(duplicate["id"])

    existing = conn.execute("SELECT word FROM words WHERE word = ?", (normalized,)).fetchone()
    if existing:
        _save_dictionary_entry(conn, normalized, dictionary_entry)
        conn.execute(
            """
            UPDATE words
            SET remaining = ?, review_interval = 0, due_date = ?,
                status = 'active', updated_at = CURRENT_TIMESTAMP
            WHERE word = ?
            """,
            (settings.graduate_after, today_key, normalized),
        )
    else:
        conn.execute(
            """
            INSERT INTO words (
                word, definitions, part_of_speech, phonetic, audio_url,
                remaining, review_interval, due_date, status
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, 'pending')
            """,
            (
                normalized,
                json.dumps(dictionary_entry.definitions, ensure_ascii=False) if dictionary_entry else "[]",
                dictionary_entry.part_of_speech if dictionary_entry else None,
                dictionary_entry.phonetic if dictionary_entry else None,
                dictionary_entry.audio_url if dictionary_entry else None,
                settings.graduate_after,
                today_key,
            ),
        )

    cursor = conn.execute(
        """
        INSERT INTO sentences (word, sentence, source_url, enriched)
        VALUES (?, ?, ?, 0)
        """,
        (normalized, normalized_sentence, source_url),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _save_dictionary_entry(conn: sqlite3.Connection, word: str, entry: DictEntry | None) -> None:
    if not entry:
        return
    row = conn.execute(
        "SELECT definitions, part_of_speech, phonetic, audio_url FROM words WHERE word = ?",
        (word,),
    ).fetchone()
    if not row:
        return
    definitions = entry.definitions or json.loads(row["definitions"] or "[]")
    conn.execute(
        """
        UPDATE words
        SET definitions = ?,
            part_of_speech = ?,
            phonetic = ?,
            audio_url = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE word = ?
        """,
        (
            json.dumps(definitions, ensure_ascii=False),
            entry.part_of_speech or row["part_of_speech"],
            entry.phonetic or row["phonetic"],
            entry.audio_url or row["audio_url"],
            word,
        ),
    )


def get_or_create_daily_deck(conn: sqlite3.Connection, settings: Settings, day: date) -> list[dict[str, Any]]:
    day_key = day.isoformat()
    existing = _load_daily_deck(conn, day_key)
    if existing:
        return existing

    return rebuild_daily_deck(conn, settings, day)


def rebuild_daily_deck(conn: sqlite3.Connection, settings: Settings, day: date) -> list[dict[str, Any]]:
    day_key = day.isoformat()
    conn.execute("DELETE FROM daily_deck WHERE date = ?", (day_key,))

    review_cards = _select_review_cards(conn, settings.daily_review_words, day_key)
    selected_words = {row["word"] for row in review_cards}
    new_cards = _select_new_cards(conn, settings.daily_new_words, selected_words)

    for row in review_cards:
        conn.execute(
            "INSERT INTO daily_deck (date, word, sentence_id, is_new) VALUES (?, ?, ?, 0)",
            (day_key, row["word"], row["sentence_id"]),
        )
    for row in new_cards:
        conn.execute(
            "UPDATE words SET status = 'active', due_date = ?, updated_at = CURRENT_TIMESTAMP WHERE word = ?",
            (day_key, row["word"]),
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
    was_answered = bool(deck_row["answered"])
    previous_correct = bool(deck_row["correct"]) if was_answered else True
    daily_correct = previous_correct and correct

    conn.execute(
        "UPDATE daily_deck SET answered = 1, correct = ? WHERE date = ? AND word = ?",
        (1 if daily_correct else 0, day_key, normalized),
    )
    conn.execute(
        "INSERT INTO reviews (word, sentence_id, correct) VALUES (?, ?, ?)",
        (normalized, deck_row["sentence_id"], 1 if correct else 0),
    )
    word_row = conn.execute(
        "SELECT review_interval FROM words WHERE word = ?", (normalized,)
    ).fetchone()
    current_interval = int(word_row["review_interval"] or 0)
    if not daily_correct:
        next_interval = 1
        due_date = (day + timedelta(days=1)).isoformat()
    elif was_answered:
        next_interval = current_interval
        due_date = conn.execute(
            "SELECT due_date FROM words WHERE word = ?", (normalized,)
        ).fetchone()["due_date"]
    else:
        next_interval = _next_good_interval(current_interval)
        due_date = (day + timedelta(days=next_interval)).isoformat()
    conn.execute(
        """
        UPDATE words
        SET review_interval = ?, due_date = ?, status = 'active', updated_at = CURRENT_TIMESTAMP
        WHERE word = ?
        """,
        (next_interval, due_date, normalized),
    )
    conn.commit()
    row = conn.execute(
        "SELECT remaining, review_interval, due_date, status FROM words WHERE word = ?", (normalized,)
    ).fetchone()
    return {
        "word": normalized,
        "already_answered": was_answered,
        "correct": daily_correct,
        "remaining": row["remaining"],
        "review_interval": row["review_interval"],
        "due_date": row["due_date"],
        "status": row["status"],
    }


def _next_good_interval(current: int) -> int:
    if current <= 0:
        return 1
    if current == 1:
        return 3
    return max(current + 1, round(current * 2.2))


def backlog_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM words WHERE status = 'active'").fetchone()
    return int(row["count"])


def total_word_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM words").fetchone()
    return int(row["count"])


def pending_enrichment_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM sentences WHERE enriched = 0").fetchone()
    return int(row["count"])


def cumulative_completed_days(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(DISTINCT date) AS count FROM daily_deck WHERE answered = 1"
    ).fetchone()
    return int(row["count"])


def cumulative_graduated_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM words WHERE status = 'graduated'"
    ).fetchone()
    return int(row["count"])


def _select_review_cards(conn: sqlite3.Connection, limit: int, day_key: str) -> list[sqlite3.Row]:
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
        WHERE w.status = 'active'
          AND (w.due_date IS NULL OR w.due_date <= ?)
        ORDER BY last_review.last_answered_at IS NOT NULL, last_review.last_answered_at ASC, w.updated_at ASC
        LIMIT ?
        """,
        (day_key, limit),
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
               w.part_of_speech, w.definitions, w.phonetic, w.audio_url,
               w.remaining, w.review_interval, w.due_date, w.status,
               s.sentence, s.answer_zh, s.definition_zh, s.trans_zh
        FROM daily_deck d
        JOIN words w ON w.word = d.word
        JOIN sentences s ON s.id = d.sentence_id
        WHERE d.date = ?
        ORDER BY d.is_new ASC, d.word ASC
        """,
        (day_key,),
    ).fetchall()
    return [_card_from_row(row) for row in rows]


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
        "review_interval": row["review_interval"],
        "due_date": row["due_date"],
        "status": row["status"],
        "answer_zh": row["answer_zh"],
        "definition_zh": row["definition_zh"],
        "trans_zh": row["trans_zh"],
    }
