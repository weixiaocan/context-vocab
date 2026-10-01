"""Pronunciation resolution for inflected forms, using trimmed real MW responses
(tests/fixtures/mw_fixtures.json, captured 2026-10-01 from the Learner's and
Collegiate v3 APIs; only meta.id/stems, hwi, fl, ins, uros and shortdef kept)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dictionary as dictionary_api
from app.api import explain
from app.backfill_dictionary import backfill, select_words
from app.config import Settings
from app.db import init_db
from app.models import DictEntry
from app.services import audio_cache, deck, dictionary

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "mw_fixtures.json").read_text(encoding="utf-8"))
MEDIA = "https://media.merriam-webster.com/audio/prons/en/us/mp3/"


def make_settings(tmp_path: Path | None = None, collegiate_key: str | None = "COLLEGIATE-SECRET") -> Settings:
    return Settings(
        daily_cards=4,
        daily_new_words=2,
        graduate_after=3,
        options_count=4,
        push_time="08:00",
        db_path=str((tmp_path or Path(".")) / "vocab.db"),
        dictionary_source="merriam_webster_learners",
        merriam_webster_dictionary_key=collegiate_key,
        merriam_webster_learners_key="LEARNERS-SECRET",
        public_base_url="http://testserver",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
        llm_enabled=False,
        feishu_webhook_url=None,
        timezone="Asia/Shanghai",
    )


@pytest.fixture
def mw(monkeypatch):
    """Fake MW API serving the captured fixtures; records which dictionaries were hit."""
    calls: list[str] = []

    def fake_get(url, params=None, timeout=None, **kwargs):
        reference, word = url.split("/references/")[1].split("/json/")
        calls.append(f"{reference}/{word}")
        assert params and params.get("key")
        payload = FIXTURES.get(f"{reference}/{word}", ["suggestion"])
        return httpx.Response(200, request=httpx.Request("GET", url), json=payload)

    monkeypatch.setattr(dictionary.httpx, "get", fake_get)
    return calls


def lookup(word: str, **kwargs) -> DictEntry:
    entry = dictionary.lookup(word, settings=make_settings(**kwargs))
    assert entry is not None
    return entry


def test_civilizations_has_no_exact_audio_and_labels_base_form(mw):
    entry = lookup("civilizations")

    # Learner's "civilization" entry has no hwi.prs at all and the plural in
    # ins has no prs; Collegiate only has the singular headword.
    assert mw == ["learners/civilizations", "collegiate/civilizations"]
    assert entry.phonetic is None
    assert entry.audio_url is None  # never silently play "civilization"
    assert entry.base_word == "civilization"
    assert entry.base_phonetic == "ˌsi-və-lə-ˈzā-shən"
    assert entry.base_audio_url == MEDIA + "c/civili05.mp3"
    assert entry.part_of_speech == "noun"
    assert entry.definitions


def test_civilizations_learners_only_still_reports_base_word(mw):
    entry = lookup("civilizations", collegiate_key=None)

    assert mw == ["learners/civilizations"]
    assert (entry.phonetic, entry.audio_url) == (None, None)
    assert entry.base_word == "civilization"


def test_tailoring_uses_its_own_phonetic_and_collegiate_audio(mw):
    entry = lookup("tailoring")

    # Learner's matches the verb "tailor" (altprs ˈteɪlɚ, no sound); the exact
    # form only appears as a run-on noun with IPA but no sound.
    assert mw == ["learners/tailoring", "collegiate/tailoring"]
    assert entry.phonetic == "ˈteɪlərɪŋ"  # not "tailor"'s ˈteɪlɚ
    assert entry.audio_url == MEDIA + "t/tailor04.mp3"
    assert entry.base_word == "tailor"
    assert entry.base_phonetic == "ˈteɪlɚ"
    assert entry.part_of_speech == "verb"


def test_tailoring_without_collegiate_key_keeps_exact_phonetic_and_no_audio(mw):
    entry = lookup("tailoring", collegiate_key=None)

    assert entry.phonetic == "ˈteɪlərɪŋ"
    assert entry.audio_url is None


def test_running_exact_headword_skips_secondary_dictionary(mw):
    entry = lookup("running")

    assert mw == ["learners/running"]
    assert entry.phonetic == "ˈrʌnɪŋ"
    assert entry.audio_url == MEDIA + "r/runnin01.mp3"
    assert entry.base_word is None


def test_studies_does_not_borrow_study_audio(mw):
    entry = lookup("studies")

    assert entry.audio_url is None
    assert entry.phonetic is None
    assert entry.base_word == "study"
    assert entry.base_audio_url == MEDIA + "s/study001.mp3"


def test_went_uses_inflection_sound_and_skips_empty_cross_reference(mw):
    entry = lookup("went")

    assert mw == ["learners/went"]
    assert entry.phonetic == "ˈwɛnt"
    assert entry.audio_url == MEDIA + "g/go000002.mp3"
    assert entry.definitions[0] == "to move or travel to a place"
    assert entry.part_of_speech == "verb"
    assert entry.base_word == "go"
    assert entry.base_audio_url == MEDIA + "g/go000001.mp3"


def test_analyses_uses_plural_audio_and_skips_cutback_phonetic(mw):
    entry = lookup("analyses")

    assert entry.audio_url == MEDIA + "a/analys03.mp3"  # not analysis' analys02
    assert entry.phonetic == "əˈnæləˌsiːz"  # full altprs, not the "-əˌsiːz" cutback
    assert entry.base_word == "analysis"


def test_multiword_headword_is_not_reported_as_base_form():
    payload = [
        {
            "meta": {"id": "quadratic equation", "stems": ["quadratic equation", "quadratic"]},
            "hwi": {"hw": "quadratic equation", "prs": [{"ipa": "kwɑˈdrætɪk-", "sound": {"audio": "quadr01ld"}}]},
            "fl": "noun",
            "shortdef": ["an equation in which the highest power of an unknown quantity is a square"],
        }
    ]

    entry = dictionary.resolve_merriam_webster("quadratic", [payload])

    assert entry is not None
    assert entry.base_word is None
    assert (entry.phonetic, entry.audio_url) == (None, None)


def test_secondary_dictionary_failure_returns_primary_result(monkeypatch):
    def fake_get(url, params=None, timeout=None, **kwargs):
        if "/collegiate/" in url:
            raise httpx.ConnectError(f"boom {params['key']}")
        return httpx.Response(200, request=httpx.Request("GET", url), json=FIXTURES["learners/tailoring"])

    monkeypatch.setattr(dictionary.httpx, "get", fake_get)
    entry = lookup("tailoring")

    assert entry.phonetic == "ˈteɪlərɪŋ"
    assert entry.audio_url is None


def test_unknown_word_suggestions_return_none(mw):
    assert dictionary.lookup("qwzx", settings=make_settings()) is None


@pytest.mark.parametrize(
    ("audio", "subdir"),
    [("bixgag01", "bix"), ("ggwhiz01", "gg"), ("3d000001", "number"), ("_01234", "number"), ("tailor04", "t")],
)
def test_mw_audio_subdirectory_rules(audio, subdir):
    assert dictionary._mw_audio_url(audio) == f"{MEDIA}{subdir}/{audio}.mp3"


# --- audio cache -----------------------------------------------------------


def memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


@pytest.fixture(autouse=True)
def clear_audio_misses():
    audio_cache._MISSES.clear()
    yield
    audio_cache._MISSES.clear()


def test_audio_cache_proxies_stored_mw_audio(tmp_path, monkeypatch):
    conn = memory_db()
    deck.collect_word(conn, make_settings(tmp_path), "tailoring", "Good tailoring.", None,
                      DictEntry(definitions=[], audio_url=MEDIA + "t/tailor04.mp3"))
    fetched = []

    def fake_get(url, timeout=None, **kwargs):
        fetched.append(url)
        return httpx.Response(200, request=httpx.Request("GET", url), content=b"ID3mp3")

    monkeypatch.setattr(audio_cache.httpx, "get", fake_get)
    monkeypatch.setattr(audio_cache.dictionary, "lookup", lambda *a, **k: pytest.fail("no lookup needed"))

    path = audio_cache.get_audio_file("tailoring", make_settings(tmp_path), conn)

    assert path is not None and path.read_bytes() == b"ID3mp3"
    assert fetched == [MEDIA + "t/tailor04.mp3"]


YOUDAO = "https://dict.youdao.com/dictvoice?audio="


def audio_response(url, content=b"ID3" + b"\x00" * 4000, content_type="audio/mpeg", status=200):
    return httpx.Response(status, request=httpx.Request("GET", url), content=content,
                          headers={"content-type": content_type})


def route_audio(monkeypatch, mw_get=None, youdao=None):
    """Patch httpx.get (shared by dictionary + audio_cache): MW API calls go to
    mw_get, Youdao calls to youdao(url), media downloads return fake mp3."""
    fetched: list[str] = []

    def fake_get(url, params=None, timeout=None, **kwargs):
        if "/references/" in url:
            return mw_get(url, params=params, timeout=timeout)
        fetched.append(url)
        if url.startswith(YOUDAO):
            return youdao(url) if youdao else audio_response(url)
        return audio_response(url)

    monkeypatch.setattr(audio_cache.httpx, "get", fake_get)
    return fetched


def test_audio_cache_falls_back_to_youdao_when_mw_has_no_exact_audio(tmp_path, monkeypatch, mw):
    mw_get = dictionary.httpx.get  # the fixture's fake MW API
    fetched = route_audio(monkeypatch, mw_get=mw_get)
    monkeypatch.setattr(dictionary, "lookup_dictionaryapi_dev", lambda *a, **k: pytest.fail("dictionaryapi.dev"))

    path = audio_cache.get_audio_file("civilizations", make_settings(tmp_path), memory_db())

    assert path is not None and path.read_bytes().startswith(b"ID3")
    # MW was consulted first, then Youdao US; the civilization (base) clip is never used.
    assert any(call.endswith("/civilizations") for call in mw)
    assert fetched == [YOUDAO + "civilizations&type=2"]
    # Cached on disk: a second request downloads nothing.
    calls_before = len(mw)
    assert audio_cache.get_audio_file("civilizations", make_settings(tmp_path), memory_db()) == path
    assert len(fetched) == 1 and len(mw) == calls_before


def test_audio_cache_prefers_exact_mw_audio_over_youdao(tmp_path, monkeypatch, mw):
    fetched = route_audio(monkeypatch, mw_get=dictionary.httpx.get)

    path = audio_cache.get_audio_file("tailoring", make_settings(tmp_path), memory_db())

    assert path is not None
    assert fetched == [MEDIA + "t/tailor04.mp3"]


def test_audio_cache_uses_youdao_when_stored_mw_download_fails(tmp_path, monkeypatch):
    conn = memory_db()
    deck.collect_word(conn, make_settings(tmp_path), "rivals", "Old rivals.", None,
                      DictEntry(definitions=[], audio_url=MEDIA + "r/rival01.mp3"))
    fetched: list[str] = []

    def fake_get(url, timeout=None, **kwargs):
        fetched.append(url)
        if url.startswith(MEDIA):
            return audio_response(url, status=404, content=b"nope", content_type="text/html")
        return audio_response(url)

    monkeypatch.setattr(audio_cache.httpx, "get", fake_get)
    assert audio_cache.get_audio_file("rivals", make_settings(tmp_path), conn) is not None
    assert fetched == [MEDIA + "r/rival01.mp3", YOUDAO + "rivals&type=2"]


def test_audio_cache_rejects_youdao_error_json_and_caches_the_miss(tmp_path, monkeypatch, mw):
    fetched = route_audio(
        monkeypatch,
        mw_get=dictionary.httpx.get,
        youdao=lambda url: audio_response(url, status=500, content=b'{"code":500}', content_type="application/json"),
    )

    assert audio_cache.get_audio_file("civilizations", make_settings(tmp_path), memory_db()) is None
    assert "civilizations" in audio_cache._MISSES
    calls_before, fetched_before = len(mw), len(fetched)
    assert audio_cache.get_audio_file("civilizations", make_settings(tmp_path), memory_db()) is None
    assert len(mw) == calls_before and len(fetched) == fetched_before  # negative result cached


def test_audio_cache_rejects_tiny_youdao_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_cache.dictionary, "lookup", lambda *a, **k: None)
    route_audio(monkeypatch, youdao=lambda url: audio_response(url, content=b"ID3"))
    assert audio_cache.get_audio_file("aces", make_settings(tmp_path), memory_db()) is None


def test_audio_cache_rejects_untrusted_hosts(tmp_path, monkeypatch):
    conn = memory_db()
    deck.collect_word(conn, make_settings(tmp_path), "evil", "An evil word.", None,
                      DictEntry(definitions=[], audio_url="https://attacker.example/x.mp3"))
    fetched: list[str] = []

    def fake_get(url, timeout=None, **kwargs):
        fetched.append(url)
        assert url.startswith(YOUDAO), f"must not fetch {url}"
        return audio_response(url)

    monkeypatch.setattr(audio_cache.httpx, "get", fake_get)
    monkeypatch.setattr(audio_cache.dictionary, "lookup", lambda *a, **k: None)

    assert audio_cache.get_audio_file("evil", make_settings(tmp_path), conn) is not None
    assert fetched == [YOUDAO + "evil&type=2"]


@pytest.mark.parametrize(
    "url, allowed",
    [
        (MEDIA + "t/tailor04.mp3", True),
        ("https://dict.youdao.com/dictvoice?audio=went&type=2", True),
        ("https://api.dictionaryapi.dev/media/pronunciations/en/went-us.mp3", True),
        ("http://dict.youdao.com/dictvoice?audio=went&type=2", False),
        ("https://dict.youdao.com.attacker.example/x.mp3", False),
        ("https://attacker.example/dict.youdao.com/x.mp3", False),
        ("https://evil@attacker.example/x.mp3", False),
        ("file:///etc/passwd", False),
        ("", False),
    ],
)
def test_audio_host_whitelist(url, allowed):
    assert audio_cache.is_allowed_audio_url(url) is allowed


def test_youdao_url_is_us_voice_and_url_encoded():
    assert audio_cache.youdao_audio_url("Went") == YOUDAO + "went&type=2"
    assert audio_cache.youdao_audio_url("o'clock") == YOUDAO + "o%27clock&type=2"
    assert audio_cache.youdao_audio_url("a&type=1#x") == YOUDAO + "a%26type%3D1%23x&type=2"
    assert audio_cache.public_audio_url("Tailoring ") == "/audio/tailoring.mp3"
    assert audio_cache.public_audio_url("a/b?c") == "/audio/a%2Fb%3Fc.mp3"


# --- storage + backfill ----------------------------------------------------


def test_collect_stores_base_form_and_review_card_exposes_it(tmp_path):
    conn = memory_db()
    settings = make_settings(tmp_path)
    entry = DictEntry(definitions=["to make clothing"], part_of_speech="verb", phonetic="ˈteɪlərɪŋ",
                      audio_url=MEDIA + "t/tailor04.mp3", base_word="tailor", base_phonetic="ˈteɪlɚ")
    sentence_id = deck.collect_word(conn, settings, "tailoring", "Good tailoring.", None, entry)
    row = conn.execute("SELECT * FROM words WHERE word = 'tailoring'").fetchone()
    assert (row["base_word"], row["base_phonetic"], row["base_audio_url"]) == ("tailor", "ˈteɪlɚ", None)
    conn.execute(
        "INSERT INTO daily_deck (date, word, sentence_id, is_new) VALUES ('2026-10-01', 'tailoring', ?, 1)",
        (sentence_id,),
    )
    card = deck._load_daily_deck(conn, "2026-10-01")[0]
    assert card["base_word"] == "tailor" and card["phonetic"] == "ˈteɪlərɪŋ"


def test_backfill_fixes_missing_and_wrong_pronunciations(tmp_path, mw):
    conn = memory_db()
    settings = make_settings(tmp_path)
    # State observed in production on 2026-10-01.
    deck.collect_word(conn, settings, "tailoring", "Good tailoring.", None,
                      DictEntry(definitions=["to make clothing"], part_of_speech="verb", phonetic="ˈteɪlɚ"))
    deck.collect_word(conn, settings, "civilizations", "Old civilizations.", None,
                      DictEntry(definitions=["a society"], part_of_speech="noun"))
    deck.collect_word(conn, settings, "studies", "He studies.", None,
                      DictEntry(definitions=["learning"], phonetic="ˈstʌdi", audio_url=MEDIA + "s/study001.mp3"))

    assert select_words(conn) == ["civilizations", "tailoring"]
    assert select_words(conn, all_words=True) == ["civilizations", "studies", "tailoring"]

    lines: list[str] = []
    stats = backfill(conn, settings, select_words(conn, all_words=True), dry_run=True, out=lines.append)
    assert stats["changed"] == 3
    assert conn.execute("SELECT phonetic FROM words WHERE word='tailoring'").fetchone()[0] == "ˈteɪlɚ"
    assert not any("SECRET" in line for line in lines)

    stats = backfill(conn, settings, select_words(conn, all_words=True), out=lines.append)
    assert stats == {"checked": 3, "changed": 3, "unchanged": 0, "not_found": 0, "failed": 0}
    rows = {r["word"]: r for r in conn.execute("SELECT * FROM words")}
    assert rows["tailoring"]["phonetic"] == "ˈteɪlərɪŋ"
    assert rows["tailoring"]["audio_url"] == MEDIA + "t/tailor04.mp3"
    assert rows["civilizations"]["audio_url"] is None
    assert rows["civilizations"]["base_audio_url"] == MEDIA + "c/civili05.mp3"
    # the wrong base-word audio previously stored on "studies" is cleared
    assert rows["studies"]["audio_url"] is None
    assert rows["studies"]["base_word"] == "study"

    again = backfill(conn, settings, select_words(conn, all_words=True), out=lines.append)
    assert again["unchanged"] == 3


def test_backfill_reports_lookup_errors_without_secrets(tmp_path):
    conn = memory_db()
    settings = make_settings(tmp_path)
    deck.collect_word(conn, settings, "tailoring", "Good tailoring.", None, None)

    def failing_lookup(word, settings=None):
        raise dictionary.DictionaryLookupError("Merriam-Webster request failed: HTTP 403")

    lines: list[str] = []
    stats = backfill(conn, settings, ["tailoring"], lookup=failing_lookup, out=lines.append)
    assert stats["failed"] == 1
    assert lines == ["fail  tailoring: Merriam-Webster request failed: HTTP 403"]


def test_lookup_and_explain_apis_expose_exact_and_base_pronunciation(tmp_path, monkeypatch, mw):
    app = FastAPI()
    app.state.db = memory_db()
    app.state.settings = make_settings(tmp_path)
    app.include_router(dictionary_api.router)
    app.include_router(explain.router)
    explain._DICT_CACHE.clear()
    monkeypatch.setattr(explain.translation, "translate_to_chinese", lambda _s, text, **kw: "文明")

    with TestClient(app) as client:
        looked_up = client.get("/dictionary/lookup", params={"word": "Civilizations"}).json()
        explained = client.post(
            "/explain", json={"term": "civilizations", "sentence": "Ancient civilizations built cities."}
        ).json()

    for body in (looked_up, explained):
        assert body["phonetic"] == "" and body["audioUrl"] == ""
        assert body["baseWord"] == "civilization"
        assert body["baseAudioUrl"] == MEDIA + "c/civili05.mp3"
    explain._DICT_CACHE.clear()
