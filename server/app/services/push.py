from __future__ import annotations

import time

import httpx

from app.config import Settings


def send_review_reminder(settings: Settings, card_count: int) -> bool:
    if not settings.feishu_webhook_url:
        return False

    review_url = settings.public_base_url.rstrip("/") + "/review"
    text = (
        f"今天有 {card_count} 张卡：{review_url}\n"
        "安卓用 Chrome 打开后，菜单选「添加到主屏幕」，可全屏复习。"
    )
    payload = {
        "msg_type": "text",
        "content": {"text": text},
    }
    for attempt in range(3):
        try:
            response = httpx.post(settings.feishu_webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            time.sleep(2**attempt)
    return False
