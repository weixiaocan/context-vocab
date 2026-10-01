from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.backfill_dictionary import main  # noqa: E402

if __name__ == "__main__":
    # Kept for backwards compatibility; same as `python -m app.backfill_dictionary --all`.
    sys.exit(main(["--all", *sys.argv[1:]]))
