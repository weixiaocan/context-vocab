from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.services import dictionary

router = APIRouter()


@router.get("/dictionary/lookup")
def lookup_word(
    request: Request,
    word: str = Query(min_length=1, max_length=80),
    sentence: str | None = Query(default=None, max_length=2000),
) -> dict[str, object]:
    normalized_word = word.strip().lower()
    try:
        entry = dictionary.lookup(normalized_word, settings=request.app.state.settings)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if entry is None:
        raise HTTPException(status_code=404, detail="word not found")
    collected = False
    if sentence and sentence.strip():
        collected = request.app.state.db.execute(
            "SELECT 1 FROM sentences WHERE word = ? AND sentence = ? LIMIT 1",
            (normalized_word, sentence.strip()),
        ).fetchone() is not None
    return {
        "word": normalized_word,
        "partOfSpeech": entry.part_of_speech or "",
        "definitions": entry.definitions,
        "phonetic": entry.phonetic or "",
        "audioUrl": entry.audio_url or "",
        "collected": collected,
    }
