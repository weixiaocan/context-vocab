"""Re-enrich stored words with dictionary phonetics/audio.

Run inside the container (the image only ships app/):

    python -m app.backfill_dictionary --dry-run          # show what would change
    python -m app.backfill_dictionary                    # words missing phonetic/audio
    python -m app.backfill_dictionary --all              # every word (fixes wrong ones too)
    python -m app.backfill_dictionary --words tailoring civilizations

Only dictionary columns are touched (definitions/part_of_speech are kept when the
new lookup has none). No secrets are printed.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from typing import Callable

from app.config import Settings, load_settings
from app.db import connect, init_db
from app.models import DictEntry
from app.redact import redact
from app.services import dictionary

PRONUNCIATION_FIELDS = ("phonetic", "audio_url", "base_word", "base_phonetic", "base_audio_url")


def select_words(conn: sqlite3.Connection, all_words: bool = False, words: list[str] | None = None) -> list[str]:
    if words:
        return [word.strip().lower() for word in words if word.strip()]
    if all_words:
        query = "SELECT word FROM words ORDER BY word"
    else:
        query = """
            SELECT word FROM words
            WHERE COALESCE(phonetic, '') = '' OR COALESCE(audio_url, '') = ''
            ORDER BY word
        """
    return [row["word"] for row in conn.execute(query)]


def backfill(
    conn: sqlite3.Connection,
    settings: Settings,
    words: list[str],
    dry_run: bool = False,
    sleep_seconds: float = 0.0,
    lookup: Callable[..., DictEntry | None] = dictionary.lookup,
    out=print,
) -> dict[str, int]:
    stats = {"checked": 0, "changed": 0, "unchanged": 0, "not_found": 0, "failed": 0}
    for index, word in enumerate(words):
        row = conn.execute(
            """
            SELECT definitions, part_of_speech, phonetic, audio_url,
                   base_word, base_phonetic, base_audio_url
            FROM words WHERE word = ?
            """,
            (word,),
        ).fetchone()
        if not row:
            continue
        stats["checked"] += 1
        if index and sleep_seconds:
            time.sleep(sleep_seconds)
        try:
            entry = lookup(word, settings=settings)
        except Exception as exc:
            stats["failed"] += 1
            out(f"fail  {word}: {redact(exc)}")
            continue
        if entry is None:
            stats["not_found"] += 1
            out(f"skip  {word}: not found")
            continue

        new_values = {field: getattr(entry, field) or None for field in PRONUNCIATION_FIELDS}
        changes = {
            field: (row[field], value)
            for field, value in new_values.items()
            if (row[field] or None) != value
        }
        definitions = entry.definitions or json.loads(row["definitions"] or "[]")
        part_of_speech = entry.part_of_speech or row["part_of_speech"]
        if not changes:
            stats["unchanged"] += 1
            continue
        stats["changed"] += 1
        summary = ", ".join(f"{field}: {old!r} -> {new!r}" for field, (old, new) in changes.items())
        out(f"{'would ' if dry_run else ''}update {word}: {summary}")
        if dry_run:
            continue
        # Pronunciation fields are overwritten (including with NULL) so that a
        # previously stored base-word pronunciation does not linger on the
        # inflected form.
        conn.execute(
            """
            UPDATE words
            SET definitions = ?, part_of_speech = ?, phonetic = ?, audio_url = ?,
                base_word = ?, base_phonetic = ?, base_audio_url = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE word = ?
            """,
            (
                json.dumps(definitions, ensure_ascii=False),
                part_of_speech,
                *(new_values[field] for field in PRONUNCIATION_FIELDS),
                word,
            ),
        )
        conn.commit()
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true", help="re-check every stored word")
    parser.add_argument("--dry-run", action="store_true", help="print changes without writing")
    parser.add_argument("--sleep", type=float, default=0.3, help="seconds between lookups")
    parser.add_argument("--words", nargs="*", help="only these words")
    args = parser.parse_args(argv)

    settings = load_settings()
    conn = connect(settings.db_path)
    init_db(conn)
    words = select_words(conn, all_words=args.all, words=args.words)
    print(f"source={settings.dictionary_source} words={len(words)} dry_run={args.dry_run}")
    stats = backfill(conn, settings, words, dry_run=args.dry_run, sleep_seconds=args.sleep)
    print("done: " + " ".join(f"{key}={value}" for key, value in stats.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
