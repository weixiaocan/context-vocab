import json
import sqlite3
from datetime import date

import pytest

from app.config import Settings
from app.db import init_db
from app.models import DictEntry
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
        SET answer_zh = ?, definition_zh = ?, trans_zh = ?, enriched = 1
        WHERE id = ?
        """,
        (
            answer,
            "数量或影响非常小的",
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


def test_collect_same_sentence_is_idempotent(conn, settings):
    first_id = deck.collect_word(conn, settings, "Warranted", "The complexity is warranted.", "https://a.test")
    conn.execute("UPDATE words SET remaining = 1, status = 'active' WHERE word = 'warranted'")
    conn.commit()

    second_id = deck.collect_word(conn, settings, "warranted", "  The complexity is warranted.  ", "https://a.test")

    word = conn.execute("SELECT remaining, status FROM words WHERE word = 'warranted'").fetchone()
    count = conn.execute("SELECT COUNT(*) AS count FROM sentences WHERE word = 'warranted'").fetchone()
    assert second_id == first_id
    assert count["count"] == 1
    assert word["remaining"] == 1
    assert word["status"] == "active"


def test_collect_saves_dictionary_result_from_extension(conn, settings):
    deck.collect_word(
        conn,
        settings,
        "Tractable",
        "The problem is tractable.",
        "https://a.test",
        DictEntry(
            definitions=["easy to deal with"],
            part_of_speech="adjective",
            phonetic="/tractable/",
            audio_url="https://audio.test/tractable.mp3",
        ),
    )

    word = conn.execute(
        "SELECT definitions, part_of_speech, phonetic, audio_url FROM words WHERE word = 'tractable'"
    ).fetchone()
    assert json.loads(word["definitions"]) == ["easy to deal with"]
    assert word["part_of_speech"] == "adjective"
    assert word["phonetic"] == "/tractable/"
    assert word["audio_url"] == "https://audio.test/tractable.mp3"


def test_recollect_same_sentence_can_fill_legacy_dictionary_fields(conn, settings):
    first_id = deck.collect_word(conn, settings, "tractable", "The problem is tractable.", None)

    second_id = deck.collect_word(
        conn,
        settings,
        "tractable",
        "The problem is tractable.",
        None,
        DictEntry(["easy to deal with"], "adjective", "/tractable/", None),
    )

    word = conn.execute("SELECT definitions, part_of_speech FROM words WHERE word = 'tractable'").fetchone()
    assert second_id == first_id
    assert json.loads(word["definitions"]) == ["easy to deal with"]
    assert word["part_of_speech"] == "adjective"


def test_daily_deck_is_stable_and_uses_enriched_pending_words(conn, settings):
    for raw_word in ["marginal", "tractable", "ablation"]:
        sentence_id = deck.collect_word(conn, settings, raw_word, f"{raw_word} sentence.", None)
        mark_enriched(conn, sentence_id, answer=f"{raw_word} 的中文义项")

    first = deck.get_or_create_daily_deck(conn, settings, date(2026, 7, 13))
    second = deck.get_or_create_daily_deck(conn, settings, date(2026, 7, 13))

    assert first == second
    assert len(first) == 2
    assert all(card["is_new"] for card in first)


def test_repeated_good_answer_records_attempt_without_expanding_twice(conn, settings):
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
    word = conn.execute(
        "SELECT review_interval, due_date, status FROM words WHERE word = 'marginal'"
    ).fetchone()

    assert result["review_interval"] == 1
    assert result["due_date"] == "2026-07-14"
    assert result["status"] == "active"
    attempts = conn.execute(
        "SELECT COUNT(*) AS count FROM reviews WHERE word = 'marginal'"
    ).fetchone()["count"]
    assert second_result["already_answered"] is True
    assert second_result["correct"] is True
    assert attempts == 2
    assert word["review_interval"] == 1
    assert word["due_date"] == "2026-07-14"
    assert word["status"] == "active"


def test_again_then_good_keeps_tomorrow_schedule_and_worst_daily_result(conn, settings):
    sentence_id = deck.collect_word(conn, settings, "marginal", "The gains appear marginal.", None)
    mark_enriched(conn, sentence_id)
    conn.execute("UPDATE words SET status = 'active', review_interval = 3 WHERE word = 'marginal'")
    conn.execute(
        "INSERT INTO daily_deck (date, word, sentence_id, is_new) VALUES (?, ?, ?, 0)",
        ("2026-07-13", "marginal", sentence_id),
    )
    conn.commit()

    first = deck.answer_card(conn, date(2026, 7, 13), "marginal", False)
    second = deck.answer_card(conn, date(2026, 7, 13), "marginal", True)
    daily = conn.execute(
        "SELECT answered, correct FROM daily_deck WHERE date = '2026-07-13' AND word = 'marginal'"
    ).fetchone()
    attempts = conn.execute(
        "SELECT correct FROM reviews WHERE word = 'marginal' ORDER BY id"
    ).fetchall()

    assert first["correct"] is False
    assert second["correct"] is False
    assert second["review_interval"] == 1
    assert second["due_date"] == "2026-07-14"
    assert daily["answered"] == 1
    assert daily["correct"] == 0
    assert [row["correct"] for row in attempts] == [0, 1]


def test_again_answer_schedules_tomorrow(conn, settings):
    sentence_id = deck.collect_word(conn, settings, "marginal", "The gains appear marginal.", None)
    mark_enriched(conn, sentence_id)
    conn.execute("UPDATE words SET status = 'active', remaining = 3 WHERE word = 'marginal'")
    conn.execute(
        "INSERT INTO daily_deck (date, word, sentence_id, is_new) VALUES (?, ?, ?, 0)",
        ("2026-07-13", "marginal", sentence_id),
    )
    conn.commit()

    deck.answer_card(conn, date(2026, 7, 13), "marginal", False)
    word = conn.execute(
        "SELECT review_interval, due_date, status FROM words WHERE word = 'marginal'"
    ).fetchone()

    assert word["review_interval"] == 1
    assert word["due_date"] == "2026-07-14"
    assert word["status"] == "active"


def test_good_answers_expand_review_interval(conn, settings):
    sentence_id = deck.collect_word(conn, settings, "marginal", "The gains appear marginal.", None)
    mark_enriched(conn, sentence_id)
    conn.execute(
        "UPDATE words SET status = 'active', review_interval = 3, due_date = '2026-07-13' WHERE word = 'marginal'"
    )
    conn.execute(
        "INSERT INTO daily_deck (date, word, sentence_id, is_new) VALUES (?, ?, ?, 0)",
        ("2026-07-13", "marginal", sentence_id),
    )
    conn.commit()

    result = deck.answer_card(conn, date(2026, 7, 13), "marginal", True)

    assert result["review_interval"] == 7
    assert result["due_date"] == "2026-07-20"


def test_cumulative_counts_only_answered_dates_and_graduated_words(conn, settings):
    for word in ["marginal", "tractable"]:
        sentence_id = deck.collect_word(conn, settings, word, f"{word} sentence.", None)
        mark_enriched(conn, sentence_id)
        conn.execute("UPDATE words SET status = 'active' WHERE word = ?", (word,))
        conn.execute(
            "INSERT INTO daily_deck (date, word, sentence_id, is_new, answered) VALUES (?, ?, ?, 0, ?)",
            ("2026-07-12", word, sentence_id, 1 if word == "marginal" else 0),
        )
    tractable_id = conn.execute(
        "SELECT id FROM sentences WHERE word = 'tractable'"
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO daily_deck (date, word, sentence_id, is_new, answered) VALUES (?, ?, ?, 0, 1)",
        ("2026-07-13", "tractable", tractable_id),
    )
    conn.execute("UPDATE words SET status = 'graduated' WHERE word = 'marginal'")
    conn.commit()

    assert deck.cumulative_completed_days(conn) == 2
    assert deck.cumulative_graduated_count(conn) == 1
