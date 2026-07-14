import json
import sqlite3
from datetime import date

import pytest

from app.config import Settings
from app.db import init_db
from app.services import deck


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        daily_cards=4,
        daily_new_words=2,
        graduate_after=3,
        options_count=4,
        push_time="08:00",
        db_path=":memory:",
        dictionary_source="dictionaryapi_dev",
        merriam_webster_dictionary_key=None,
        merriam_webster_learners_key=None,
        public_base_url="http://testserver",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
        llm_enabled=False,
        feishu_webhook_url=None,
        timezone="Asia/Shanghai",
    )


@pytest.fixture()
def conn() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    init_db(db)
    return db


def mark_enriched(conn: sqlite3.Connection, sentence_id: int, answer: str = "微小的") -> None:
    conn.execute(
        """
        UPDATE sentences
        SET answer_zh = ?, distractors = ?, trans_zh = ?, enriched = 1
        WHERE id = ?
        """,
        (
            answer,
            json.dumps(["边缘的", "次要的", "有限的"], ensure_ascii=False),
            "进一步扩展带来的收益似乎很小。",
            sentence_id,
        ),
    )
    conn.commit()


def test_collect_duplicate_appends_sentence_and_resets_progress(conn, settings):
    first_id = deck.collect_word(conn, settings, "Marginal", "The gains appear marginal.", "https://a.test")
    mark_enriched(conn, first_id)
    deck.get_or_create_daily_deck(conn, settings, date(2026, 7, 13))
    deck.answer_card(conn, date(2026, 7, 13), "marginal", True)

    second_id = deck.collect_word(conn, settings, "marginal", "The effect was marginal.", "https://b.test")

    word = conn.execute("SELECT remaining, status FROM words WHERE word = 'marginal'").fetchone()
    count = conn.execute("SELECT COUNT(*) AS count FROM sentences WHERE word = 'marginal'").fetchone()
    assert second_id != first_id
    assert word["remaining"] == 3
    assert word["status"] == "active"
    assert count["count"] == 2


def test_daily_deck_is_stable_and_uses_enriched_pending_words(conn, settings):
    for raw_word in ["marginal", "tractable", "ablation"]:
        sentence_id = deck.collect_word(conn, settings, raw_word, f"{raw_word} sentence.", None)
        mark_enriched(conn, sentence_id, answer=f"{raw_word} 的中文义项")

    first = deck.get_or_create_daily_deck(conn, settings, date(2026, 7, 13))
    second = deck.get_or_create_daily_deck(conn, settings, date(2026, 7, 13))

    assert first == second
    assert len(first) == 2
    assert all(card["is_new"] for card in first)


def test_answer_correct_decrements_once_and_graduates(conn, settings):
    sentence_id = deck.collect_word(conn, settings, "marginal", "The gains appear marginal.", None)
    mark_enriched(conn, sentence_id)
    conn.execute("UPDATE words SET status = 'active', remaining = 1 WHERE word = 'marginal'")
    conn.execute(
        "INSERT INTO daily_deck (date, word, sentence_id, is_new) VALUES (?, ?, ?, 0)",
        ("2026-07-13", "marginal", sentence_id),
    )
    conn.commit()

    result = deck.answer_card(conn, date(2026, 7, 13), "marginal", True)
    second_result = deck.answer_card(conn, date(2026, 7, 13), "marginal", True)
    word = conn.execute("SELECT remaining, status FROM words WHERE word = 'marginal'").fetchone()

    assert result["remaining"] == 0
    assert result["status"] == "graduated"
    assert second_result["already_answered"] is True
    assert word["remaining"] == 0
    assert word["status"] == "graduated"


def test_answer_wrong_does_not_decrement(conn, settings):
    sentence_id = deck.collect_word(conn, settings, "marginal", "The gains appear marginal.", None)
    mark_enriched(conn, sentence_id)
    conn.execute("UPDATE words SET status = 'active', remaining = 3 WHERE word = 'marginal'")
    conn.execute(
        "INSERT INTO daily_deck (date, word, sentence_id, is_new) VALUES (?, ?, ?, 0)",
        ("2026-07-13", "marginal", sentence_id),
    )
    conn.commit()

    deck.answer_card(conn, date(2026, 7, 13), "marginal", False)
    word = conn.execute("SELECT remaining, status FROM words WHERE word = 'marginal'").fetchone()

    assert word["remaining"] == 3
    assert word["status"] == "active"
