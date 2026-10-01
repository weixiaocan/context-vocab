from __future__ import annotations

import logging
import re

# Query parameters whose values must never reach logs or error messages
# (Merriam-Webster ?key=, Baidu appid/sign, generic tokens).
_SECRET_PARAM = re.compile(
    r"(?i)\b(key|api_key|apikey|appid|sign|token|access_token)=([^&\s'\"<>]+)"
)
_REDACTED = "***"

_QUIET_LOGGERS = ("httpx", "httpcore")
_EXTRA_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def redact(text: object) -> str:
    """Mask secret-looking query parameter values in ``text``."""
    return _SECRET_PARAM.sub(lambda m: f"{m.group(1)}={_REDACTED}", str(text))


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - malformed record, let logging report it
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = None
        return True


def _attach_filter(logger: logging.Logger) -> None:
    for handler in logger.handlers:
        if not any(isinstance(item, RedactingFilter) for item in handler.filters):
            handler.addFilter(RedactingFilter())


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level)
    # httpx logs every request URL at INFO, which includes ?key=<api key>.
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    _attach_filter(logging.getLogger())
    for name in _EXTRA_LOGGERS:
        _attach_filter(logging.getLogger(name))
