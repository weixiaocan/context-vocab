from __future__ import annotations

import json
import sqlite3

from app.config import Settings
from app.services import dictionary, llm


def enrich_pending(conn: sqlite3.Connection, settings: Settings, limit: int = 20) -> int:
    rows = conn.execute(
        """
        SELECT s.id, s.word, s.sentence, w.definitions
        FROM sentences s
        JOIN words w ON w.word = s.word
        WHERE s.enriched = 0
        ORDER BY s.created_at ASC, s.id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    completed = 0
    for row in rows:
        _ensure_dictionary_fields(conn, settings, row["word"])
        word_row = conn.execute("SELECT definitions FROM words WHERE word = ?", (row["word"],)).fetchone()
        definitions = json.loads(word_row["definitions"] or "[]")
        try:
            enriched = llm.enrich_sentence(settings, row["word"], row["sentence"], definitions)
        except Exception:
            continue

        conn.execute(
            """
            UPDATE sentences
            SET answer_zh = ?, distractors = ?, trans_zh = ?, enriched = 1
            WHERE id = ?
            """,
            (
                enriched.answer_zh,
                json.dumps(enriched.distractors, ensure_ascii=False),
                enriched.trans_zh,
                row["id"],
            ),
        )
        completed += 1
    conn.commit()
    return completed


def _ensure_dictionary_fields(conn: sqlite3.Connection, settings: Settings, word: str) -> None:
    row = conn.execute(
        "SELECT definitions, part_of_speech, phonetic, audio_url FROM words WHERE word = ?",
        (word,),
    ).fetchone()
    if not row:
        return
    definitions = json.loads(row["definitions"] or "[]")
    if definitions or row["part_of_speech"] or row["phonetic"] or row["audio_url"]:
        return

    try:
        entry = dictionary.lookup(word, settings=settings)
    except Exception:
        entry = None
    if not entry:
        return

    conn.execute(
        """
        UPDATE words
        SET definitions = ?, part_of_speech = ?, phonetic = ?, audio_url = ?, updated_at = CURRENT_TIMESTAMP
        WHERE word = ?
        """,
        (
            json.dumps(entry.definitions, ensure_ascii=False),
            entry.part_of_speech,
            entry.phonetic,
            entry.audio_url,
            word,
        ),
    )
