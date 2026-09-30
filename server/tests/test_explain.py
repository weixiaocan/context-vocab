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
