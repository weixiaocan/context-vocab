import httpx
import pytest

from app.services import dictionary
from app.services.dictionary import DictionaryLookupError
from app.services.dictionary import parse_dictionaryapi_dev, parse_merriam_webster


def test_parse_merges_phonetic_and_prefers_us_audio():
    payload = [
        {
            "word": "marginal",
            "phonetics": [
                {"text": "/ˈmɑː.dʒɪ.nəl/"},
                {"audio": "https://example.com/marginal-au.mp3"},
                {"audio": "https://example.com/marginal-us.mp3"},
            ],
            "meanings": [
                {
                    "partOfSpeech": "adjective",
                    "definitions": [
                        {"definition": "Very small in amount or effect."},
                        {"definition": "At the edge of something."},
                        {"definition": "Barely within a lower standard."},
                        {"definition": "Extra definition that should be trimmed."},
                    ],
                }
            ],
        }
    ]

    entry = parse_dictionaryapi_dev(payload)

    assert entry is not None
    assert entry.part_of_speech == "adjective"
    assert entry.phonetic == "/ˈmɑː.dʒɪ.nəl/"
    assert entry.audio_url == "https://example.com/marginal-us.mp3"
    assert entry.definitions == [
        "Very small in amount or effect.",
        "At the edge of something.",
        "Barely within a lower standard.",
    ]


def test_parse_allows_missing_audio():
    payload = [
        {
            "word": "scaling",
            "phonetics": [{"text": "/ˈskeɪ.lɪŋ/"}],
            "meanings": [{"partOfSpeech": "noun", "definitions": [{"definition": "The act of changing size."}]}],
        }
    ]

    entry = parse_dictionaryapi_dev(payload)

    assert entry is not None
    assert entry.audio_url is None
    assert entry.phonetic == "/ˈskeɪ.lɪŋ/"


def test_parse_merriam_webster_learners_entry():
    payload = [
        {
            "meta": {"id": "marginal"},
            "hwi": {
                "hw": "marginal",
                "prs": [{"ipa": "ˈmɑrʤənəl", "sound": {"audio": "margin01"}}],
            },
            "fl": "adjective",
            "shortdef": [
                "not very important",
                "very slight or small",
                "not included in the main part of society or of a group",
                "trimmed",
            ],
        }
    ]

    entry = parse_merriam_webster(payload)

    assert entry is not None
    assert entry.part_of_speech == "adjective"
    assert entry.phonetic == "ˈmɑrʤənəl"
    assert entry.audio_url == "https://media.merriam-webster.com/audio/prons/en/us/mp3/m/margin01.mp3"
    assert entry.definitions == [
        "not very important",
        "very slight or small",
        "not included in the main part of society or of a group",
    ]


def test_parse_merriam_webster_suggestion_list_returns_none():
    assert parse_merriam_webster(["demystify", "mystify"]) is None


def test_parse_merriam_webster_uses_alternate_pronunciation_without_audio():
    payload = [
        {
            "meta": {"id": "warrant:2"},
            "hwi": {"hw": "warrant", "altprs": [{"ipa": "ˈworənt"}]},
            "fl": "verb",
            "shortdef": ["to require or deserve (something)"],
        }
    ]

    entry = parse_merriam_webster(payload)

    assert entry is not None
    assert entry.phonetic == "ˈworənt"
    assert entry.audio_url is None


MW_URL = "https://www.dictionaryapi.com/api/v3/references/collegiate/json/guardrails"


def test_merriam_webster_http_error_does_not_leak_key(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(403, request=request, text="forbidden")

    monkeypatch.setattr(dictionary.httpx, "get", fake_get)
    with pytest.raises(DictionaryLookupError) as info:
        dictionary._lookup_merriam_webster(MW_URL, "SUPERSECRET123", 1.0)

    assert "SUPERSECRET123" not in str(info.value)
    assert "403" in str(info.value)
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ is True


def test_merriam_webster_transport_error_does_not_leak_key(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise httpx.ConnectError(f"cannot reach {url}?key={params['key']}")

    monkeypatch.setattr(dictionary.httpx, "get", fake_get)
    with pytest.raises(DictionaryLookupError) as info:
        dictionary._lookup_merriam_webster(MW_URL, "SUPERSECRET123", 1.0)

    assert "SUPERSECRET123" not in str(info.value)
