from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.models import DictEntry


class DictionaryLookupError(RuntimeError):
    pass


def lookup(word: str, settings: Settings | None = None, timeout: float = 8.0) -> DictEntry | None:
    if settings and settings.dictionary_source == "merriam_webster_learners":
        return lookup_merriam_webster_learners(word, settings, timeout=timeout)
    if settings and settings.dictionary_source == "merriam_webster_collegiate":
        return lookup_merriam_webster_collegiate(word, settings, timeout=timeout)
    return lookup_dictionaryapi_dev(word, timeout=timeout)


def lookup_dictionaryapi_dev(word: str, timeout: float = 8.0) -> DictEntry | None:
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
    try:
        response = httpx.get(url, timeout=timeout)
    except httpx.HTTPError as exc:
        raise DictionaryLookupError(str(exc)) from exc

    if response.status_code == 404:
        return None
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        return None
    return parse_dictionaryapi_dev(payload)


def lookup_merriam_webster_learners(word: str, settings: Settings, timeout: float = 8.0) -> DictEntry | None:
    if not settings.merriam_webster_learners_key:
        raise DictionaryLookupError("MERRIAM_WEBSTER_LEARNERS_KEY is missing")
    url = f"https://www.dictionaryapi.com/api/v3/references/learners/json/{word}"
    return _lookup_merriam_webster(url, settings.merriam_webster_learners_key, timeout)


def lookup_merriam_webster_collegiate(word: str, settings: Settings, timeout: float = 8.0) -> DictEntry | None:
    if not settings.merriam_webster_dictionary_key:
        raise DictionaryLookupError("MERRIAM_WEBSTER_DICTIONARY_KEY is missing")
    url = f"https://www.dictionaryapi.com/api/v3/references/collegiate/json/{word}"
    return _lookup_merriam_webster(url, settings.merriam_webster_dictionary_key, timeout)


def _lookup_merriam_webster(url: str, api_key: str, timeout: float) -> DictEntry | None:
    try:
        response = httpx.get(url, params={"key": api_key}, timeout=timeout)
    except httpx.HTTPError as exc:
        raise DictionaryLookupError(str(exc)) from exc
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload or isinstance(payload[0], str):
        return None
    return parse_merriam_webster(payload)


def parse_dictionaryapi_dev(payload: list[dict[str, Any]]) -> DictEntry | None:
    entry = payload[0]
    meanings = entry.get("meanings") or []
    if not meanings:
        return DictEntry(definitions=[], phonetic=_merge_phonetic(entry).get("phonetic"), audio_url=_merge_phonetic(entry).get("audio_url"))

    best_meaning = meanings[0]
    definitions = [
        item.get("definition", "").strip()
        for item in best_meaning.get("definitions", [])
        if item.get("definition")
    ][:3]
    merged = _merge_phonetic(entry)
    return DictEntry(
        definitions=definitions,
        part_of_speech=best_meaning.get("partOfSpeech"),
        phonetic=merged.get("phonetic"),
        audio_url=merged.get("audio_url"),
    )


def parse_merriam_webster(payload: list[dict[str, Any]]) -> DictEntry | None:
    entry = next((item for item in payload if isinstance(item, dict)), None)
    if not entry:
        return None
    definitions = [
        _strip_mw_markup(item)
        for item in entry.get("shortdef", [])
        if isinstance(item, str) and item.strip()
    ][:3]
    pronunciation = _extract_mw_pronunciation(entry)
    return DictEntry(
        definitions=definitions,
        part_of_speech=entry.get("fl"),
        phonetic=pronunciation.get("phonetic"),
        audio_url=pronunciation.get("audio_url"),
    )


def _extract_mw_pronunciation(entry: dict[str, Any]) -> dict[str, str | None]:
    hwi = entry.get("hwi") or {}
    pronunciations = [*(hwi.get("prs") or []), *(hwi.get("altprs") or [])]
    phonetic = None
    audio_url = None
    for item in pronunciations:
        if not isinstance(item, dict):
            continue
        if not phonetic:
            phonetic = item.get("ipa") or item.get("mw")
        sound = item.get("sound") or {}
        audio = sound.get("audio")
        if audio and not audio_url:
            audio_url = _mw_audio_url(audio)
    return {"phonetic": phonetic, "audio_url": audio_url}


def _mw_audio_url(audio: str) -> str:
    if audio.startswith("bix"):
        subdir = "bix"
    elif audio.startswith("gg"):
        subdir = "gg"
    elif audio[0].isdigit() or audio[0] in {"_", "-"}:
        subdir = "number"
    else:
        subdir = audio[0]
    return f"https://media.merriam-webster.com/audio/prons/en/us/mp3/{subdir}/{audio}.mp3"


def _strip_mw_markup(text: str) -> str:
    replacements = {
        "{bc}": "",
        "{sx|": "",
        "{d_link|": "",
        "{a_link|": "",
        "{it}": "",
        "{/it}": "",
    }
    clean = text
    for old, new in replacements.items():
        clean = clean.replace(old, new)
    clean = clean.replace("||", " ")
    clean = clean.replace("|", " ")
    clean = clean.replace("{", "").replace("}", "")
    return " ".join(clean.split())


def _merge_phonetic(entry: dict[str, Any]) -> dict[str, str | None]:
    phonetics = entry.get("phonetics") or []
    phonetic = None
    audio_candidates: list[str] = []

    for item in phonetics:
        if not phonetic and item.get("text"):
            phonetic = item["text"]
        audio = (item.get("audio") or "").strip()
        if audio:
            audio_candidates.append(audio)

    audio_url = None
    if audio_candidates:
        audio_url = next(
            (
                audio
                for audio in audio_candidates
                if "-us" in audio.lower() or "us.mp3" in audio.lower()
            ),
            audio_candidates[0],
        )

    return {"phonetic": phonetic, "audio_url": audio_url}
