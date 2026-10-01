from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, HTTPException, Request

from app.models import DictEntry, ExplainRequest
from app.redact import redact
from app.services import dictionary, translation

router = APIRouter()
logger = logging.getLogger(__name__)

# Process-wide cache of successful dictionary lookups so repeated /explain calls
# for uncollected words do not hit Merriam-Webster every time.
_DICT_CACHE: dict[tuple[str, str], DictEntry] = {}
_DICT_CACHE_MAX = 1024


@router.post("/explain")
def explain_selection(payload: ExplainRequest, request: Request) -> dict[str, object]:
    term = _normalize_term(payload.term)
    sentence = _normalize_sentence(payload.sentence)
    if not term:
        raise HTTPException(status_code=422, detail="selection is not a supported English word or phrase")
    if term.lower() not in sentence.lower():
        raise HTTPException(status_code=422, detail="sentence must contain the selected term")

    conn = request.app.state.db
    cached = conn.execute(
        "SELECT answer_zh, trans_zh FROM translation_cache WHERE term = ? AND sentence = ?",
        (term, sentence),
    ).fetchone()
    collected = conn.execute(
        "SELECT 1 FROM sentences WHERE word = ? AND sentence = ? LIMIT 1",
        (term, sentence),
    ).fetchone() is not None
    entry = _dictionary_entry(conn, request, term)

    if cached:
        answer_zh = cached["answer_zh"]
        trans_zh = cached["trans_zh"]
    else:
        try:
            answer_zh = translation.translate_to_chinese(
                request.app.state.settings, term, context=sentence
            )
            trans_zh = (
                answer_zh
                if term.casefold() == sentence.casefold()
                else translation.translate_to_chinese(request.app.state.settings, sentence)
            )
        except translation.TranslationError as exc:
            raise HTTPException(status_code=502, detail=redact(exc)) from exc
        conn.execute(
            """
            INSERT OR REPLACE INTO translation_cache (term, sentence, answer_zh, trans_zh)
            VALUES (?, ?, ?, ?)
            """,
            (term, sentence, answer_zh, trans_zh),
        )
        conn.commit()

    return {
        "term": term,
        "answer_zh": answer_zh,
        "definition_zh": answer_zh,
        "trans_zh": trans_zh,
        "partOfSpeech": (entry.part_of_speech or "") if entry else "",
        "definitions": entry.definitions if entry else [],
        "phonetic": (entry.phonetic or "") if entry else "",
        "audioUrl": (entry.audio_url or "") if entry else "",
        "collected": collected,
    }


def _normalize_term(value: str) -> str:
    compact = " ".join(value.split()).strip(" \t\r\n.,;:!?()[]{}\"“”‘’")
    if not compact or not re.fullmatch(r"[A-Za-z](?:[A-Za-z'’\- ]{0,78}[A-Za-z])?", compact):
        return ""
    return compact.replace("’", "'").lower()


def _normalize_sentence(value: str) -> str:
    return " ".join(value.split()).strip()[:2000]


def _dictionary_entry(conn, request: Request, term: str) -> DictEntry | None:
    if " " in term:
        return None
    row = conn.execute(
        "SELECT definitions, part_of_speech, phonetic, audio_url FROM words WHERE word = ?",
        (term,),
    ).fetchone()
    if row and any((row["definitions"], row["part_of_speech"], row["phonetic"], row["audio_url"])):
        return DictEntry(
            definitions=json.loads(row["definitions"] or "[]"),
            part_of_speech=row["part_of_speech"],
            phonetic=row["phonetic"],
            audio_url=row["audio_url"],
        )
    settings = request.app.state.settings
    cache_key = (str(getattr(settings, "dictionary_source", "")), term)
    cached = _DICT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        entry = dictionary.lookup(term, settings=settings)
    except Exception as exc:
        logger.warning("dictionary lookup failed for %r: %s", term, redact(exc))
        return None
    if entry is not None:
        if len(_DICT_CACHE) >= _DICT_CACHE_MAX:
            _DICT_CACHE.pop(next(iter(_DICT_CACHE)))
        _DICT_CACHE[cache_key] = entry
    return entry
