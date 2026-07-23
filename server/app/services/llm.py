from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.models import EnrichedSentence


class LLMError(RuntimeError):
    pass


def enrich_sentence(
    settings: Settings,
    word: str,
    sentence: str,
    definitions: list[str],
) -> EnrichedSentence:
    if not settings.llm_enabled:
        raise LLMError("LLM is disabled")
    if not settings.deepseek_api_key:
        raise LLMError("DEEPSEEK_API_KEY is missing")

    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "enrich.txt"
    prompt = prompt_path.read_text(encoding="utf-8")
    user_payload = {
        "word": word,
        "sentence": sentence,
        "dictionary_definitions": definitions,
    }

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            data = _call_deepseek(settings, prompt, user_payload)
            return _parse_enriched(data)
        except Exception as exc:  # noqa: BLE001 - retry boundary
            last_error = exc
            time.sleep(2**attempt)
    raise LLMError(str(last_error))


def _call_deepseek(settings: Settings, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
    url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
    response = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return json.loads(content)


def _parse_enriched(data: dict[str, Any]) -> EnrichedSentence:
    answer = str(data.get("answer_zh", "")).strip()
    definition = str(data.get("definition_zh", "")).strip()
    translation = str(data.get("trans_zh", "")).strip()
    if not answer or not definition or not translation:
        raise LLMError("LLM response missing answer_zh, definition_zh, or trans_zh")
    return EnrichedSentence(answer_zh=answer, definition_zh=definition, trans_zh=translation)
