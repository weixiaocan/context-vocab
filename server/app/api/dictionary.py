from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.services import dictionary

router = APIRouter()


@router.get("/dictionary/lookup")
def lookup_word(request: Request, word: str = Query(min_length=1, max_length=80)) -> dict[str, object]:
    try:
        entry = dictionary.lookup(word.strip().lower(), settings=request.app.state.settings)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if entry is None:
        raise HTTPException(status_code=404, detail="word not found")
    return {
        "word": word.strip().lower(),
        "partOfSpeech": entry.part_of_speech or "",
        "definitions": entry.definitions,
        "phonetic": entry.phonetic or "",
        "audioUrl": entry.audio_url or "",
    }
