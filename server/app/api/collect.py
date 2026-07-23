from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request

from app.models import CollectWordRequest, DictEntry
from app.services import deck, enrich

router = APIRouter()


@router.post("/words")
def collect_word(payload: CollectWordRequest, request: Request, background_tasks: BackgroundTasks) -> dict[str, object]:
    sentence_id = deck.collect_word(
        request.app.state.db,
        request.app.state.settings,
        payload.word,
        payload.sentence,
        payload.source_url,
        DictEntry(
            definitions=payload.definitions,
            part_of_speech=payload.part_of_speech,
            phonetic=payload.phonetic,
            audio_url=payload.audio_url,
        ),
    )
    background_tasks.add_task(enrich.enrich_pending, request.app.state.db, request.app.state.settings, 5)
    return {"ok": True, "word": payload.word.strip().lower(), "sentence_id": sentence_id}
