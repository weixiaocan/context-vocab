from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    daily_cards: int
    daily_new_words: int
    graduate_after: int
    options_count: int
    push_time: str
    db_path: str
    dictionary_source: str
    merriam_webster_dictionary_key: str | None
    merriam_webster_learners_key: str | None
    public_base_url: str
    deepseek_api_key: str | None
    deepseek_base_url: str
    deepseek_model: str
    llm_enabled: bool
    feishu_webhook_url: str | None
    timezone: str
    access_token: str | None = None
    translation_provider: str = "auto"
    baidu_app_id: str | None = None
    baidu_secret: str | None = None
    baidu_base_url: str = "https://fanyi-api.baidu.com/api/trans/vip/translate"
    tencent_translation_api_key: str | None = None
    tencent_translation_base_url: str = "https://tokenhub.tencentmaas.com/v1"
    tencent_translation_model: str = "hy-mt2-plus"

    @property
    def daily_review_words(self) -> int:
        return max(self.daily_cards - self.daily_new_words, 0)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_settings(config_path: str | Path | None = None) -> Settings:
    base_dir = Path(__file__).resolve().parents[1]
    load_dotenv(base_dir / ".env")

    path = Path(config_path) if config_path else base_dir / "config.yaml"
    data: dict[str, Any] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    settings = Settings(
        daily_cards=int(data.get("daily_cards", 10)),
        daily_new_words=int(data.get("daily_new_words", 5)),
        graduate_after=int(data.get("graduate_after", 3)),
        options_count=int(data.get("options_count", 4)),
        push_time=str(data.get("push_time", "08:00")),
        db_path=str(data.get("db_path", "./data/vocab.db")),
        dictionary_source=str(data.get("dictionary_source", "dictionaryapi_dev")),
        merriam_webster_dictionary_key=os.getenv("MERRIAM_WEBSTER_DICTIONARY_KEY"),
        merriam_webster_learners_key=os.getenv("MERRIAM_WEBSTER_LEARNERS_KEY"),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        llm_enabled=_as_bool(os.getenv("LLM_ENABLED"), True),
        tencent_translation_api_key=os.getenv("TENCENT_TRANSLATION_API_KEY"),
        tencent_translation_base_url=os.getenv(
            "TENCENT_TRANSLATION_BASE_URL", "https://tokenhub.tencentmaas.com/v1"
        ),
        tencent_translation_model=os.getenv("TENCENT_TRANSLATION_MODEL", "hy-mt2-plus"),
        feishu_webhook_url=os.getenv("FEISHU_WEBHOOK_URL"),
        timezone=str(data.get("timezone", "Asia/Shanghai")),
        access_token=os.getenv("ACCESS_TOKEN"),
        translation_provider=os.getenv("TRANSLATION_PROVIDER", "auto"),
        baidu_app_id=os.getenv("BAIDU_APP_ID"),
        baidu_secret=os.getenv("BAIDU_SECRET"),
        baidu_base_url=os.getenv(
            "BAIDU_BASE_URL", "https://fanyi-api.baidu.com/api/trans/vip/translate"
        ),
    )
    _validate(settings)
    return settings


def _validate(settings: Settings) -> None:
    if settings.daily_cards <= 0:
        raise ValueError("daily_cards must be positive")
    if settings.daily_new_words < 0:
        raise ValueError("daily_new_words must be non-negative")
    if settings.daily_new_words > settings.daily_cards:
        raise ValueError("daily_new_words must be <= daily_cards")
    if settings.graduate_after <= 0:
        raise ValueError("graduate_after must be positive")
    if settings.options_count != 4:
        raise ValueError("v1 expects options_count to be 4")
