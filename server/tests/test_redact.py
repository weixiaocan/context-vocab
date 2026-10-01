import logging

from app.redact import RedactingFilter, configure_logging, redact


def test_redact_masks_secret_query_params():
    text = "GET https://x.test/json/word?key=abc-123&foo=bar and appid=42&sign=deadbeef"
    cleaned = redact(text)
    assert "abc-123" not in cleaned
    assert "deadbeef" not in cleaned
    assert "key=***" in cleaned
    assert "foo=bar" in cleaned


def test_redacting_filter_rewrites_log_records():
    record = logging.LogRecord(
        "httpx", logging.INFO, __file__, 1,
        'HTTP Request: GET %s "HTTP/1.1 200 OK"',
        ("https://www.dictionaryapi.com/api/v3/x/json/w?key=SECRET",),
        None,
    )
    assert RedactingFilter().filter(record) is True
    assert "SECRET" not in record.getMessage()
    assert "key=***" in record.getMessage()


def test_configure_logging_silences_httpx_info():
    configure_logging(logging.INFO)
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
