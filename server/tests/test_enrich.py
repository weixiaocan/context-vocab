import sqlite3

from app.config import Settings
from app.db import init_db
from app.models import DictEntry, EnrichedSentence
from app.services import deck, enrich


def test_enrich_pending_keeps_dictionary_optional(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    settings = Settings(
        daily_cards=10,
        daily_new_words=5,
        graduate_after=3,
        options_count=4,
        push_time="08:00",
        db_path=":memory:",
        dictionary_source="dictionaryapi_dev",
        merriam_webster_dictionary_key=None,
        merriam_webster_learners_key=None,
        public_base_url="http://testserver",
        deepseek_api_key="fake",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
        llm_enabled=True,
        feishu_webhook_url=None,
        timezone="Asia/Shanghai",
    )
    deck.collect_word(conn, settings, "marginal", "The gains appear marginal.", None)

    monkeypatch.setattr(enrich.dictionary, "lookup", lambda word, settings=None: None)
    monkeypatch.setattr(
        enrich.llm,
        "enrich_sentence",
        lambda settings, word, sentence, definitions: EnrichedSentence(
            answer_zh="微小的",
            definition_zh="数量或影响非常小的",
            trans_zh="进一步扩展带来的收益似乎很小。",
        ),
    )

    completed = enrich.enrich_pending(conn, settings)
    row = conn.execute("SELECT enriched, answer_zh FROM sentences").fetchone()

    assert completed == 1
    assert row["enriched"] == 1
    assert row["answer_zh"] == "微小的"


def test_enrich_pending_saves_dictionary_fields(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    settings = Settings(
        daily_cards=10,
        daily_new_words=5,
        graduate_after=3,
        options_count=4,
        push_time="08:00",
        db_path=":memory:",
        dictionary_source="dictionaryapi_dev",
        merriam_webster_dictionary_key=None,
        merriam_webster_learners_key=None,
        public_base_url="http://testserver",
        deepseek_api_key="fake",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
        llm_enabled=True,
        feishu_webhook_url=None,
        timezone="Asia/Shanghai",
    )
    deck.collect_word(conn, settings, "tractable", "The problem is tractable.", None)
    monkeypatch.setattr(
        enrich.dictionary,
        "lookup",
        lambda word, settings=None: DictEntry(["easy to deal with"], "adjective", "/ˈtræk.tə.bəl/", "https://example.com/us.mp3"),
    )
    monkeypatch.setattr(
        enrich.llm,
        "enrich_sentence",
        lambda settings, word, sentence, definitions: EnrichedSentence(
            answer_zh="易处理的",
            definition_zh="容易处理或解决的",
            trans_zh="这个问题是易处理的。",
        ),
    )

    enrich.enrich_pending(conn, settings)
    row = conn.execute("SELECT definitions, part_of_speech, phonetic, audio_url FROM words").fetchone()

    assert "easy to deal with" in row["definitions"]
    assert row["part_of_speech"] == "adjective"
    assert row["phonetic"] == "/ˈtræk.tə.bəl/"
    assert row["audio_url"] == "https://example.com/us.mp3"


def test_enrich_pending_reuses_dictionary_fields_saved_at_collection(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    settings = Settings(
        daily_cards=10,
        daily_new_words=5,
        graduate_after=3,
        options_count=4,
        push_time="08:00",
        db_path=":memory:",
        dictionary_source="dictionaryapi_dev",
        merriam_webster_dictionary_key=None,
        merriam_webster_learners_key=None,
        public_base_url="http://testserver",
        deepseek_api_key="fake",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
        llm_enabled=True,
        feishu_webhook_url=None,
        timezone="Asia/Shanghai",
    )
    deck.collect_word(
        conn,
        settings,
        "tractable",
        "The problem is tractable.",
        None,
        DictEntry(["easy to deal with"], "adjective", "/tractable/", None),
    )

    def unexpected_lookup(word, settings=None):
        raise AssertionError("dictionary lookup should not run for stored fields")

    monkeypatch.setattr(enrich.dictionary, "lookup", unexpected_lookup)
    monkeypatch.setattr(
        enrich.llm,
        "enrich_sentence",
        lambda settings, word, sentence, definitions: EnrichedSentence(
            answer_zh="易处理的",
            definition_zh="容易处理或解决的",
            trans_zh="这个问题是易处理的。",
        ),
    )

    assert enrich.enrich_pending(conn, settings) == 1
