from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import Settings
from app.db import connect, init_db
from app.services import enrich, push

logger = logging.getLogger(__name__)


def start_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.timezone)
    hour, minute = [int(part) for part in settings.push_time.split(":", 1)]
    scheduler.add_job(lambda: _send_push(settings), "cron", hour=hour, minute=minute)
    scheduler.add_job(lambda: _run_enrich(settings), "interval", minutes=10)
    scheduler.start()
    return scheduler


def _send_push(settings: Settings) -> None:
    conn = connect(settings.db_path)
    try:
        init_db(conn)
        ok = push.send_review_reminder(settings, settings.daily_cards)
        if not ok:
            logger.error("Feishu push failed or webhook is not configured")
    finally:
        conn.close()


def _run_enrich(settings: Settings) -> None:
    conn = connect(settings.db_path)
    try:
        init_db(conn)
        completed = enrich.enrich_pending(conn, settings, limit=20)
        if completed:
            logger.info("Enriched %s pending sentences", completed)
    finally:
        conn.close()
