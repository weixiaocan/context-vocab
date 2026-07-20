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
