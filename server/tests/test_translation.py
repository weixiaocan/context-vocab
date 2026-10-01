import httpx
import pytest

from app.config import Settings
from app.services import translation
from app.services.translation import TranslationError, translate_to_chinese


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch):
    """Replace the throttle clock/sleep so tests never really sleep."""
    clock = {"now": 1000.0, "sleeps": []}

    def fake_sleep(seconds):
        clock["sleeps"].append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(translation, "_sleep", fake_sleep)
    monkeypatch.setattr(translation, "_monotonic", lambda: clock["now"])
    monkeypatch.setattr(translation, "_baidu_last_request", 0.0)
    return clock


def settings(
    *,
    provider: str = "auto",
    baidu_app_id: str | None = None,
    baidu_secret: str | None = None,
    tencent_key: str | None = None,
) -> Settings:
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
        translation_provider=provider,
        baidu_app_id=baidu_app_id,
        baidu_secret=baidu_secret,
        tencent_translation_api_key=tencent_key,
        tencent_translation_base_url="https://tokenhub.tencentmaas.com/v1",
        tencent_translation_model="hy-mt2-plus",
    )


def test_translate_prefers_baidu_when_credentials_present():
    captured = {}

    def requester(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(
            200,
            json={"trans_result": [{"src": "tractable", "dst": "易处理的"}]},
            request=httpx.Request("GET", url),
        )

    result = translate_to_chinese(
        settings(baidu_app_id="appid", baidu_secret="secret"),
        " tractable ",
        context="The problem is tractable.",
        requester=requester,
    )

    assert result == "易处理的"
    assert captured["url"] == "https://fanyi-api.baidu.com/api/trans/vip/translate"
    params = captured["params"]
    assert params["q"] == "tractable"
    assert params["from"] == "en"
    assert params["to"] == "zh"
    assert params["appid"] == "appid"
    assert len(params["salt"]) == 6
    assert len(params["sign"]) == 32


def test_baidu_error_code_raises_translation_error():
    def requester(url, **kwargs):
        return httpx.Response(
            200,
            json={"error_code": "54001", "error_msg": "sign error"},
            request=httpx.Request("GET", url),
        )

    with pytest.raises(TranslationError, match="54001"):
        translate_to_chinese(
            settings(provider="baidu", baidu_app_id="appid", baidu_secret="secret"),
            "tractable",
            requester=requester,
        )


def test_translate_falls_back_to_tencent_without_baidu_credentials():
    captured = {}

    def requester(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "易于处理的"}}]},
            request=httpx.Request("POST", url),
        )

    result = translate_to_chinese(
        settings(tencent_key="tokenhub-key"),
        "tractable",
        context="The problem is tractable.",
        requester=requester,
    )

    assert result == "易于处理的"
    assert captured["url"] == "https://tokenhub.tencentmaas.com/v1/api/translations"
    assert captured["headers"]["Authorization"] == "Bearer tokenhub-key"
    assert captured["json"] == {
        "model": "hy-mt2-plus",
        "text": "tractable",
        "source": "en",
        "target": "zh",
        "stream": False,
        "context": "The problem is tractable.",
    }


def test_translate_requires_tencent_api_key_when_selected():
    with pytest.raises(TranslationError, match="TENCENT_TRANSLATION_API_KEY is missing"):
        translate_to_chinese(
            settings(provider="tencent"),
            "tractable",
        )


def test_translate_without_any_credentials_reports_configuration_error():
    with pytest.raises(TranslationError, match="no translation credentials"):
        translate_to_chinese(settings(), "tractable")


def _baidu_settings():
    return settings(provider="baidu", baidu_app_id="appid", baidu_secret="secret")


def test_baidu_rate_limit_54003_is_retried(fake_clock):
    responses = [
        {"error_code": "54003", "error_msg": "Invalid Access Limit"},
        {"trans_result": [{"src": "guardrails", "dst": "\u62a4\u680f"}]},
    ]
    calls = []

    def requester(url, **kwargs):
        calls.append(kwargs["params"]["q"])
        return httpx.Response(200, json=responses.pop(0), request=httpx.Request("GET", url))

    result = translate_to_chinese(_baidu_settings(), "guardrails", requester=requester)

    assert result == "\u62a4\u680f"
    assert calls == ["guardrails", "guardrails"]
    assert fake_clock["sleeps"] == [pytest.approx(1.1)]


def test_baidu_rate_limit_gives_up_after_two_retries(fake_clock):
    calls = []

    def requester(url, **kwargs):
        calls.append(1)
        return httpx.Response(
            200,
            json={"error_code": 54003, "error_msg": "Invalid Access Limit"},
            request=httpx.Request("GET", url),
        )

    with pytest.raises(TranslationError, match="54003"):
        translate_to_chinese(_baidu_settings(), "guardrails", requester=requester)
    assert len(calls) == 3
    assert len(fake_clock["sleeps"]) == 2


def test_baidu_calls_are_throttled(fake_clock):
    def requester(url, **kwargs):
        return httpx.Response(
            200,
            json={"trans_result": [{"src": "a", "dst": "b"}]},
            request=httpx.Request("GET", url),
        )

    translate_to_chinese(_baidu_settings(), "first", requester=requester)
    fake_clock["now"] += 0.3
    translate_to_chinese(_baidu_settings(), "second", requester=requester)

    assert fake_clock["sleeps"] == [pytest.approx(0.8)]
    assert translation._BAIDU_MIN_INTERVAL >= 1.05


def test_baidu_http_error_message_is_redacted():
    def requester(url, **kwargs):
        request = httpx.Request("GET", url, params=kwargs["params"])
        return httpx.Response(500, request=request)

    with pytest.raises(TranslationError) as info:
        translate_to_chinese(_baidu_settings(), "guardrails", requester=requester)
    message = str(info.value)
    assert "sign=***" in message
    assert "appid=***" in message
