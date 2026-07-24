from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services import dictionary


def public_audio_url(word: str) -> str:
    return f"/audio/{quote(word.strip().lower())}.mp3"


def get_audio_file(word: str, settings: Settings) -> Path | None:
    cache_dir = Path(settings.db_path).resolve().parent / "audio"
    cache_dir.mkdir(parents=True, exist_ok=True)
    filename = "".join(char for char in word.lower() if char.isalnum() or char in {"-", "_"})
    if not filename:
        return None
    target = cache_dir / f"{filename}.mp3"
    if target.exists() and target.stat().st_size:
        return target
    entry = None
    for candidate in _audio_candidates(word):
        entry = dictionary.lookup_dictionaryapi_dev(candidate)
        if entry and entry.audio_url:
            break
    if not entry or not entry.audio_url:
        return None
    response = httpx.get(entry.audio_url, timeout=10.0)
    response.raise_for_status()
    target.write_bytes(response.content)
    return target


def _audio_candidates(word: str) -> list[str]:
    normalized = word.strip().lower()
    candidates = [normalized]
    for suffix in ("ing", "ed", "es", "s"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix) + 2:
            stem = normalized[: -len(suffix)]
            candidates.append(stem)
            if suffix == "ing" and len(stem) > 1 and stem[-1] == stem[-2]:
                candidates.append(stem[:-1])
    return list(dict.fromkeys(candidates))
