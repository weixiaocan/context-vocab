from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from app.config import Settings
from app.redact import redact
from app.services import dictionary

logger = logging.getLogger(__name__)

# Hosts we are willing to download pronunciation audio from. audio_url values
# can come from the browser extension, so never fetch arbitrary URLs.
ALLOWED_AUDIO_HOSTS = frozenset(
    {"media.merriam-webster.com", "api.dictionaryapi.dev", "dict.youdao.com"}
)

# Youdao dictvoice: type=2 is US English (matches Merriam-Webster), type=1 UK.
YOUDAO_VOICE_URL = "https://dict.youdao.com/dictvoice?audio={word}&type=2"
# Youdao answers unknown words with HTTP 500 + JSON; real clips are several KB.
_MIN_AUDIO_BYTES = 1024

# Words recently found to have no audio from any source. Avoids hitting the
# dictionaries on every tap of the speaker button (the client falls back to TTS).
_MISS_TTL_SECONDS = 6 * 3600
_MISSES: dict[str, float] = {}

# Cache subdirectory. The pre-v2 cache (data/audio/*.mp3) was filled from
# dictionaryapi.dev and may hold base-word audio, so it is not reused.
_CACHE_SUBDIR = "v2"


def public_audio_url(word: str) -> str:
    return f"/audio/{quote(word.strip().lower(), safe='')}.mp3"


def youdao_audio_url(word: str) -> str:
    return YOUDAO_VOICE_URL.format(word=quote(word.strip().lower(), safe=""))


def get_audio_file(
    word: str, settings: Settings, conn: sqlite3.Connection | None = None
) -> Path | None:
    """Return a cached mp3 of the *exact* word's pronunciation, or None.

    Source priority: (1) the Merriam-Webster recording of this exact form
    (stored audio_url, else a fresh lookup), (2) Youdao dictvoice (US) for the
    word. Each word is downloaded once and cached on disk. Never substitutes
    the base word's audio (see commit c7155c3): when nothing is found the
    caller returns 404 and the client speaks the word with TTS.
    """
    cache_dir = Path(settings.db_path).resolve().parent / "audio" / _CACHE_SUBDIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    normalized = word.strip().lower()
    filename = "".join(char for char in normalized if char.isalnum() or char in {"-", "_"})
    if not filename:
        return None
    target = cache_dir / f"{filename}.mp3"
    if target.exists() and target.stat().st_size:
        return target
    missed_at = _MISSES.get(normalized)
    if missed_at and time.monotonic() - missed_at < _MISS_TTL_SECONDS:
        return None

    for source, url_factory in audio_sources(normalized, settings, conn):
        url = url_factory()
        if not url or not is_allowed_audio_url(url):
            continue
        content = _download(url)
        if content is None:
            continue
        partial = target.with_suffix(".mp3.part")
        partial.write_bytes(content)
        partial.replace(target)
        logger.info("cached %s audio for %r", source, normalized)
        return target
    _MISSES[normalized] = time.monotonic()
    return None


def audio_sources(word: str, settings: Settings, conn: sqlite3.Connection | None):
    """Ordered (name, lazy url) candidates; lazy so later sources cost nothing
    when an earlier one succeeds."""
    stored = _stored_audio_url(conn, word)
    if stored:
        yield "merriam-webster", lambda: stored
    else:
        yield "merriam-webster", lambda: _lookup_audio_url(word, settings)
    yield "youdao", lambda: youdao_audio_url(word)


def is_allowed_audio_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_AUDIO_HOSTS


def _download(url: str) -> bytes | None:
    try:
        response = httpx.get(url, timeout=10.0, follow_redirects=False)
    except httpx.HTTPError as exc:
        logger.warning("audio download failed (%s): %s", urlparse(url).hostname, redact(exc))
        return None
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if response.status_code != 200 or not response.content:
        logger.info("audio unavailable (%s): HTTP %s", urlparse(url).hostname, response.status_code)
        return None
    # Youdao signals misses with JSON; MW may omit a precise type, so only
    # reject explicit non-audio responses, and require a plausible size.
    if content_type and not (content_type.startswith("audio/") or content_type == "application/octet-stream"):
        logger.info("audio rejected (%s): content-type %s", urlparse(url).hostname, content_type)
        return None
    if urlparse(url).hostname == "dict.youdao.com" and len(response.content) < _MIN_AUDIO_BYTES:
        return None
    return response.content


def _stored_audio_url(conn: sqlite3.Connection | None, word: str) -> str | None:
    if conn is None:
        return None
    row = conn.execute("SELECT audio_url FROM words WHERE word = ?", (word,)).fetchone()
    return (row["audio_url"] or None) if row else None


def _lookup_audio_url(word: str, settings: Settings) -> str | None:
    # Use the configured dictionary (Merriam-Webster in production). The old
    # hard-coded dictionaryapi.dev lookup times out from the server.
    try:
        entry = dictionary.lookup(word, settings=settings)
    except Exception as exc:
        logger.warning("audio lookup failed for %r: %s", word, redact(exc))
        return None
    return entry.audio_url if entry else None
