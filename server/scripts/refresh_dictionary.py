from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import load_settings  # noqa: E402
from app.db import connect, init_db  # noqa: E402
from app.services.dictionary import lookup  # noqa: E402


def main() -> None:
    settings = load_settings()
    conn = connect(settings.db_path)
    init_db(conn)
    rows = conn.execute("SELECT word FROM words ORDER BY word").fetchall()
    updated = 0
    for row in rows:
        word = row["word"]
        entry = lookup(word, settings=settings)
        if not entry:
            print(f"skip {word}: not found")
            continue
        conn.execute(
            """
            UPDATE words
            SET definitions = ?, part_of_speech = ?, phonetic = ?, audio_url = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE word = ?
            """,
            (
                json.dumps(entry.definitions, ensure_ascii=False),
                entry.part_of_speech,
                entry.phonetic,
                entry.audio_url,
                word,
            ),
        )
        updated += 1
        print(f"updated {word}")
    conn.commit()
    print(f"done: {updated}/{len(rows)} updated")


if __name__ == "__main__":
    main()
