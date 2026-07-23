import sqlite3

from app.db import init_db


def test_init_db_migrates_existing_cards_for_new_review_format():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE words (
            word TEXT PRIMARY KEY,
            part_of_speech TEXT,
            definitions TEXT,
            phonetic TEXT,
            audio_url TEXT,
            remaining INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL,
            sentence TEXT NOT NULL,
            source_url TEXT,
            answer_zh TEXT,
            distractors TEXT,
            trans_zh TEXT,
            enriched INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO words (word, definitions, remaining, status)
        VALUES ('tractable', '[]', 3, 'active');
        INSERT INTO sentences (word, sentence, answer_zh, distractors, trans_zh, enriched)
        VALUES ('tractable', 'The problem is tractable.', '易处理的', '[]', '这个问题易于处理。', 1);
        """
    )

    init_db(conn)

    word_columns = {row["name"] for row in conn.execute("PRAGMA table_info(words)")}
    sentence_columns = {row["name"] for row in conn.execute("PRAGMA table_info(sentences)")}
    sentence = conn.execute("SELECT enriched FROM sentences").fetchone()
    assert {"review_interval", "due_date"} <= word_columns
    assert "definition_zh" in sentence_columns
    assert sentence["enriched"] == 0
