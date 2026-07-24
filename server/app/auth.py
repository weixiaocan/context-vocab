from __future__ import annotations

import secrets


COOKIE_NAME = "vocab_access"


def valid_access_token(expected: str | None, supplied: str | None) -> bool:
    if not expected:
        return True
    if not supplied:
        return False
    return secrets.compare_digest(expected, supplied)
