from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.models import DictEntry
from app.redact import redact

logger = logging.getLogger(__name__)


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


_MW_ENDPOINTS = {
    "learners": "https://www.dictionaryapi.com/api/v3/references/learners/json/",
    "collegiate": "https://www.dictionaryapi.com/api/v3/references/collegiate/json/",
}


def lookup_merriam_webster_learners(word: str, settings: Settings, timeout: float = 8.0) -> DictEntry | None:
    if not settings.merriam_webster_learners_key:
        raise DictionaryLookupError("MERRIAM_WEBSTER_LEARNERS_KEY is missing")
    return _lookup_merriam_webster_sources(
        word,
        primary=("learners", settings.merriam_webster_learners_key),
        secondary=("collegiate", settings.merriam_webster_dictionary_key),
        timeout=timeout,
    )


def lookup_merriam_webster_collegiate(word: str, settings: Settings, timeout: float = 8.0) -> DictEntry | None:
    if not settings.merriam_webster_dictionary_key:
        raise DictionaryLookupError("MERRIAM_WEBSTER_DICTIONARY_KEY is missing")
    return _lookup_merriam_webster_sources(
        word,
        primary=("collegiate", settings.merriam_webster_dictionary_key),
        secondary=("learners", settings.merriam_webster_learners_key),
        timeout=timeout,
    )


def _lookup_merriam_webster_sources(
    word: str,
    primary: tuple[str, str],
    secondary: tuple[str, str | None],
    timeout: float,
) -> DictEntry | None:
    """Look the word up in the primary MW dictionary and, only when the primary
    has no pronunciation of this *exact* form, in the secondary one.

    Example: Learner's has no sound for "tailoring" (only the verb "tailor"),
    while Collegiate has a "tailoring" headword with audio tailor04.
    """
    primary_payload = _fetch_merriam_webster(_mw_url(primary[0], word), primary[1], timeout)
    payloads = [primary_payload] if primary_payload else []
    if not secondary[1] or (payloads and _exact_pronunciation_complete(word, payloads)):
        return resolve_merriam_webster(word, payloads)
    try:
        secondary_payload = _fetch_merriam_webster(_mw_url(secondary[0], word), secondary[1], timeout)
    except DictionaryLookupError as exc:
        logger.warning("secondary Merriam-Webster lookup failed for %r: %s", word, exc)
        secondary_payload = None
    if secondary_payload:
        payloads.append(secondary_payload)
    return resolve_merriam_webster(word, payloads)


def _mw_url(reference: str, word: str) -> str:
    return _MW_ENDPOINTS[reference] + quote(word.strip(), safe="")


def _fetch_merriam_webster(url: str, api_key: str, timeout: float) -> list[dict[str, Any]] | None:
    # Never let the request URL (which carries ?key=) into messages or chained
    # tracebacks: build our own message and suppress the original exception.
    try:
        response = httpx.get(url, params={"key": api_key}, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise DictionaryLookupError(
            f"Merriam-Webster request failed: HTTP {exc.response.status_code}"
        ) from None
    except httpx.HTTPError as exc:
        message = redact(str(exc)).replace(api_key, "***")
        raise DictionaryLookupError(
            f"Merriam-Webster request failed: {type(exc).__name__}: {message}"
        ) from None
    except ValueError:
        raise DictionaryLookupError("Merriam-Webster returned invalid JSON") from None
    if not isinstance(payload, list) or not payload or isinstance(payload[0], str):
        return None
    return [item for item in payload if isinstance(item, dict)] or None


def _lookup_merriam_webster(url: str, api_key: str, timeout: float) -> DictEntry | None:
    payload = _fetch_merriam_webster(url, api_key, timeout)
    if not payload:
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


def parse_merriam_webster(payload: list[dict[str, Any]], word: str | None = None) -> DictEntry | None:
    entries = [item for item in payload if isinstance(item, dict)]
    if not entries:
        return None
    if word is None:
        word = _mw_headword(entries[0])
    return resolve_merriam_webster(word, [entries])


def resolve_merriam_webster(word: str, payloads: list[list[dict[str, Any]]]) -> DictEntry | None:
    """Build a DictEntry for ``word`` from one or more MW payloads (primary first).

    phonetic/audio_url only ever describe the exact form that was looked up
    (headword, inflection ``ins`` or run-on ``uros`` spelled exactly like the
    word). They are never silently borrowed from the base word -- "studies"
    must not play "study" (see commit c7155c3). When the definitions come from
    a different headword (e.g. "tailoring" -> "tailor"), that headword and its
    own pronunciation are returned separately as base_word/base_phonetic/
    base_audio_url so the UI can label them explicitly.
    """
    target = _mw_clean(word)
    payloads = [[item for item in payload if isinstance(item, dict)] for payload in payloads if payload]
    payloads = [payload for payload in payloads if payload]
    if not target or not payloads:
        return None

    definition_entry = next(
        (entry for payload in payloads if (entry := _mw_definition_entry(target, payload))), None
    )
    if definition_entry is None:
        return None
    definitions = [
        _strip_mw_markup(item)
        for item in definition_entry.get("shortdef", [])
        if isinstance(item, str) and item.strip()
    ][:3]

    phonetic, audio_url = _pick_pronunciation(
        pron for payload in payloads for pron in _mw_exact_pronunciations(target, payload)
    )

    base_word = _mw_headword(definition_entry)
    base_phonetic = base_audio_url = None
    # Multi-word headwords ("quadratic equation") are not a base form of a single word.
    if base_word and base_word != target and " " not in base_word:
        base_phonetic, base_audio_url = _pick_pronunciation(
            pron
            for payload in payloads
            for entry in payload
            if _mw_headword(entry) == base_word
            for pron in _mw_prs(entry.get("hwi") or {})
        )
    else:
        base_word = None

    return DictEntry(
        definitions=definitions,
        part_of_speech=definition_entry.get("fl"),
        phonetic=phonetic,
        audio_url=audio_url,
        base_word=base_word,
        base_phonetic=base_phonetic,
        base_audio_url=base_audio_url,
    )


def _exact_pronunciation_complete(word: str, payloads: list[list[dict[str, Any]]]) -> bool:
    target = _mw_clean(word)
    phonetic, audio_url = _pick_pronunciation(
        pron for payload in payloads for pron in _mw_exact_pronunciations(target, payload)
    )
    return bool(phonetic and audio_url)


def _mw_clean(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    return " ".join(text.replace("*", "").replace("\u2019", "'").split()).casefold()


def _mw_headword(entry: dict[str, Any]) -> str:
    hw = _mw_clean((entry.get("hwi") or {}).get("hw"))
    if hw:
        return hw
    meta_id = (entry.get("meta") or {}).get("id")
    return _mw_clean(meta_id.split(":", 1)[0]) if isinstance(meta_id, str) else ""


def _mw_definition_entry(target: str, payload: list[dict[str, Any]]) -> dict[str, Any] | None:
    with_defs = [
        entry
        for entry in payload
        if any(isinstance(item, str) and item.strip() for item in entry.get("shortdef") or [])
    ]
    exact = next((entry for entry in with_defs if _mw_headword(entry) == target), None)
    if exact:
        return exact
    stems = next(
        (
            entry
            for entry in with_defs
            if target in {_mw_clean(stem) for stem in (entry.get("meta") or {}).get("stems") or []}
        ),
        None,
    )
    return stems or (with_defs[0] if with_defs else None)


def _mw_exact_pronunciations(target: str, payload: list[dict[str, Any]]) -> list[tuple[str | None, str | None]]:
    found: list[tuple[str | None, str | None]] = []
    for entry in payload:
        if _mw_headword(entry) == target:
            found.extend(_mw_prs(entry.get("hwi") or {}))
        for inflection in entry.get("ins") or []:
            if isinstance(inflection, dict) and _mw_clean(inflection.get("if")) == target:
                found.extend(_mw_prs(inflection))
        for run_on in entry.get("uros") or []:
            if isinstance(run_on, dict) and _mw_clean(run_on.get("ure")) == target:
                found.extend(_mw_prs(run_on))
    return found


def _mw_prs(container: dict[str, Any]) -> list[tuple[str | None, str | None]]:
    result = []
    for item in [*(container.get("prs") or []), *(container.get("altprs") or [])]:
        if not isinstance(item, dict):
            continue
        phonetic = (item.get("ipa") or item.get("mw") or "").strip() or None
        audio = ((item.get("sound") or {}).get("audio") or "").strip()
        result.append((phonetic, _mw_audio_url(audio) if audio else None))
    return result


def _pick_pronunciation(prons) -> tuple[str | None, str | None]:
    phonetic = audio_url = None
    for candidate_phonetic, candidate_audio in prons:
        # MW abbreviates some inflection pronunciations ("-əˌsiːz"); a cut-back
        # fragment is not a usable phonetic on its own.
        if not phonetic and candidate_phonetic and not _is_partial(candidate_phonetic):
            phonetic = candidate_phonetic
        if not audio_url and candidate_audio:
            audio_url = candidate_audio
    return phonetic, audio_url


def _is_partial(phonetic: str) -> bool:
    return phonetic.startswith(("-", "\u2011")) or phonetic.endswith(("-", "\u2011"))


def _mw_audio_url(audio: str) -> str:
    if audio.startswith("bix"):
        subdir = "bix"
    elif audio.startswith("gg"):
        subdir = "gg"
    elif not audio[0].isalpha():
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
