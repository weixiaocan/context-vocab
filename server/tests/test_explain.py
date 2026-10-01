import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import explain
from app.config import Settings
from app.db import init_db


def make_settings() -> Settings:
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
        tencent_translation_api_key="tokenhub-key",
    )


def test_explain_supports_phrases_and_caches_exact_context(monkeypatch):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    app = FastAPI()
    app.state.db = conn
    app.state.settings = make_settings()
    app.include_router(explain.router)

    calls = []

    def fake_translate(_settings, text, **kwargs):
        calls.append((text, kwargs.get("context")))
        return "简而言之" if text == "in a nutshell" else "简而言之，这是可行的。"

    monkeypatch.setattr(explain.translation, "translate_to_chinese", fake_translate)
    payload = {
        "term": "In a nutshell",
        "sentence": "In a nutshell, this is tractable.",
    }

    with TestClient(app) as client:
        first = client.post("/explain", json=payload)
        second = client.post("/explain", json=payload)

    assert first.status_code == 200
    assert first.json()["answer_zh"] == "简而言之"
    assert first.json()["trans_zh"] == "简而言之，这是可行的。"
    assert first.json()["definitions"] == []
    assert second.json() == first.json()
    assert calls == [
        ("in a nutshell", "In a nutshell, this is tractable."),
        ("In a nutshell, this is tractable.", None),
    ]
    conn.close()


def test_explain_includes_phonetic_and_audio_from_cached_dictionary(monkeypatch):
    from app.models import DictEntry

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    app = FastAPI()
    app.state.db = conn
    app.state.settings = make_settings()
    app.include_router(explain.router)
    explain._DICT_CACHE.clear()

    lookups = []

    def fake_lookup(word, settings=None, timeout=8.0):
        lookups.append(word)
        return DictEntry(
            definitions=["a protective rail"],
            part_of_speech="noun",
            phonetic="\u02c8g\u00e4rd-\u02ccr\u0101l",
            audio_url="https://media.merriam-webster.com/audio/prons/en/us/mp3/g/guard02.mp3",
        )

    monkeypatch.setattr(explain.dictionary, "lookup", fake_lookup)
    monkeypatch.setattr(
        explain.translation, "translate_to_chinese", lambda _s, text, **kw: "\u62a4\u680f"
    )

    with TestClient(app) as client:
        first = client.post(
            "/explain", json={"term": "guardrails", "sentence": "Add guardrails to the model."}
        )
        second = client.post(
            "/explain", json={"term": "guardrails", "sentence": "We need guardrails here."}
        )

    assert first.status_code == 200 and second.status_code == 200
    body = first.json()
    assert body["answer_zh"] == "\u62a4\u680f"
    assert body["phonetic"] == "\u02c8g\u00e4rd-\u02ccr\u0101l"
    assert body["audioUrl"].startswith("https://media.merriam-webster.com/")
    assert second.json()["audioUrl"] == body["audioUrl"]
    assert lookups == ["guardrails"]
    explain._DICT_CACHE.clear()
    conn.close()
