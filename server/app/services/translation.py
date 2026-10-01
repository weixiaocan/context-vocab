from __future__ import annotations

import hashlib
import random
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.config import Settings
from app.redact import redact


class TranslationError(RuntimeError):
    pass


# Baidu standard tier is QPS=1; serialize calls and space them out so concurrent
# lookups (and the term + sentence pair in one /explain) stay within the limit.
_baidu_lock = threading.Lock()
_baidu_last_request = 0.0
_BAIDU_MIN_INTERVAL = 1.1
# 54003 = "Invalid Access Limit" (QPS exceeded): back off and retry.
_BAIDU_RATE_LIMIT_CODE = "54003"
_BAIDU_RATE_LIMIT_RETRIES = 2
_BAIDU_RETRY_DELAY = 1.1


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _monotonic() -> float:
    return time.monotonic()


def translate_to_chinese(
    settings: Settings,
    text: str,
    *,
    context: str | None = None,
    timeout: float = 20.0,
    requester: Callable[..., httpx.Response] | None = None,
) -> str:
    source_text = " ".join(text.split()).strip()
    if not source_text:
        raise TranslationError("text is empty")

    provider = _select_provider(settings)
    if provider == "baidu":
        return _translate_baidu(
            settings, source_text, timeout=timeout, requester=requester or httpx.get
        )
    if provider == "tencent":
        return _translate_tencent(
            settings,
            source_text,
            context=context,
            timeout=timeout,
            requester=requester or httpx.post,
        )
    raise TranslationError(
        "no translation credentials configured: set BAIDU_APP_ID and BAIDU_SECRET, "
        "or TENCENT_TRANSLATION_API_KEY"
    )


def _select_provider(settings: Settings) -> str | None:
    preferred = (settings.translation_provider or "auto").strip().lower()
    if preferred in {"baidu", "tencent"}:
        return preferred
    if settings.baidu_app_id and settings.baidu_secret:
        return "baidu"
    if settings.tencent_translation_api_key:
        return "tencent"
    return None


def _translate_baidu(
    settings: Settings,
    text: str,
    *,
    timeout: float,
    requester: Callable[..., httpx.Response],
) -> str:
    if not settings.baidu_app_id or not settings.baidu_secret:
        raise TranslationError("BAIDU_APP_ID and BAIDU_SECRET are missing")

    salt = str(random.randrange(100_000, 1_000_000))
    sign = hashlib.md5(
        f"{settings.baidu_app_id}{text}{salt}{settings.baidu_secret}".encode("utf-8")
    ).hexdigest()
    params: dict[str, str] = {
        "q": text,
        "from": "en",
        "to": "zh",
        "appid": settings.baidu_app_id,
        "salt": salt,
        "sign": sign,
    }

    data: Any = None
    for attempt in range(_BAIDU_RATE_LIMIT_RETRIES + 1):
        data = _baidu_request(settings.baidu_base_url, params, timeout, requester)
        if _is_baidu_rate_limited(data) and attempt < _BAIDU_RATE_LIMIT_RETRIES:
            _sleep(_BAIDU_RETRY_DELAY)
            continue
        break
    return _parse_baidu(data)


def _is_baidu_rate_limited(data: Any) -> bool:
    return isinstance(data, dict) and str(data.get("error_code", "")) == _BAIDU_RATE_LIMIT_CODE


def _baidu_request(
    url: str,
    params: dict[str, str],
    timeout: float,
    requester: Callable[..., httpx.Response],
) -> Any:
    global _baidu_last_request
    with _baidu_lock:
        remaining = _baidu_last_request + _BAIDU_MIN_INTERVAL - _monotonic()
        if remaining > 0:
            _sleep(remaining)
        _baidu_last_request = _monotonic()
        try:
            response = requester(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TranslationError(redact(exc)) from None


def _parse_baidu(data: dict[str, Any]) -> str:
    if not isinstance(data, dict) or "error_code" in data:
        code = data.get("error_code", "unknown") if isinstance(data, dict) else "unknown"
        msg = data.get("error_msg", "") if isinstance(data, dict) else ""
        raise TranslationError(f"Baidu translation error {code}: {msg}")
    results = data.get("trans_result")
    if not isinstance(results, list) or not results:
        raise TranslationError("Baidu translation response is missing trans_result")
    parts = [
        str(item.get("dst", "")).strip()
        for item in results
        if isinstance(item, dict)
    ]
    translated = "\n".join(part for part in parts if part).strip()
    if not translated:
        raise TranslationError("Baidu translation returned empty content")
    return translated


def _translate_tencent(
    settings: Settings,
    text: str,
    *,
    context: str | None,
    timeout: float,
    requester: Callable[..., httpx.Response],
) -> str:
    if not settings.tencent_translation_api_key:
        raise TranslationError("TENCENT_TRANSLATION_API_KEY is missing")

    url = f"{settings.tencent_translation_base_url.rstrip('/')}/api/translations"
    payload: dict[str, Any] = {
        "model": settings.tencent_translation_model,
        "text": text,
        "source": "en",
        "target": "zh",
        "stream": False,
    }
    normalized_context = " ".join((context or "").split()).strip()
    if normalized_context and normalized_context != text:
        payload["context"] = normalized_context

    try:
        response = requester(
            url,
            headers={
                "Authorization": f"Bearer {settings.tencent_translation_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TranslationError(redact(exc)) from None

    try:
        translated = str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise TranslationError(
            "Tencent translation response is missing translated content"
        ) from exc
    if not translated:
        raise TranslationError("Tencent translation returned empty content")
    return translated
