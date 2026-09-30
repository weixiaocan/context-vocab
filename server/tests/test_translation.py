import httpx
import pytest

from app.config import Settings
from app.services.translation import TranslationError, translate_to_chinese


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
