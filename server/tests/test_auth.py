from app.auth import valid_access_token
from app.config import Settings
from fastapi.testclient import TestClient

import app.main as main


def test_missing_config_keeps_local_development_compatible():
    assert valid_access_token(None, None) is True


def test_configured_token_is_required_and_must_match():
    assert valid_access_token("secret", None) is False
    assert valid_access_token("secret", "wrong") is False
    assert valid_access_token("secret", "secret") is True


def test_app_remembers_browser_login_and_rejects_unauthorized_api(monkeypatch, tmp_path):
    settings = Settings(
        daily_cards=10,
        daily_new_words=5,
        graduate_after=3,
        options_count=4,
        push_time="08:00",
        db_path=str(tmp_path / "vocab.db"),
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
        access_token="secret",
    )

    class Scheduler:
        def shutdown(self, wait=False):
            pass

    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main, "start_scheduler", lambda _settings: Scheduler())

    with TestClient(main.create_app()) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/dictionary/lookup?word=test").status_code == 401
        redirect = client.get("/review", follow_redirects=False)
        assert redirect.status_code == 303
        assert redirect.headers["location"] == "/login?next=/review"
        assert client.post("/login", json={"token": "wrong"}).status_code == 401
        assert client.post("/login", json={"token": "secret"}).status_code == 200
        assert client.get("/review").status_code == 200
