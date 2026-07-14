from __future__ import annotations

import time

import httpx

from app.config import Settings


def send_review_reminder(settings: Settings, card_count: int) -> bool:
    if not settings.feishu_webhook_url:
        return False

    review_url = settings.public_base_url.rstrip("/") + "/review"
    payload = {
        "msg_type": "text",
        "content": {"text": f"今天有 {card_count} 张卡：{review_url}"},
    }
    for attempt in range(3):
        try:
            response = httpx.post(settings.feishu_webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            time.sleep(2**attempt)
    return False
