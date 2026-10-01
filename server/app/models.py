from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field, model_validator


class CollectWordRequest(BaseModel):
    word: str = Field(min_length=1, max_length=80)
    sentence: str = Field(min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2000)
    definitions: list[str] = Field(default_factory=list, max_length=3)
    part_of_speech: str | None = Field(default=None, max_length=80)
    phonetic: str | None = Field(default=None, max_length=200)
    audio_url: str | None = Field(default=None, max_length=2000)
    base_word: str | None = Field(default=None, max_length=80)
    base_phonetic: str | None = Field(default=None, max_length=200)
    base_audio_url: str | None = Field(default=None, max_length=2000)
    answer_zh: str | None = Field(default=None, max_length=500)
    definition_zh: str | None = Field(default=None, max_length=2000)
    trans_zh: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def enrichment_is_complete(self) -> "CollectWordRequest":
        values = (self.answer_zh, self.definition_zh, self.trans_zh)
        if any(value is not None for value in values) and not all(
            value is not None and value.strip() for value in values
        ):
            raise ValueError("answer_zh, definition_zh, and trans_zh must be supplied together")
        return self


class ExplainRequest(BaseModel):
    term: str = Field(min_length=1, max_length=80)
    sentence: str = Field(min_length=1, max_length=2000)


class ReviewAnswerRequest(BaseModel):
    word: str = Field(min_length=1, max_length=80)
    correct: bool


@dataclass(frozen=True)
class DictEntry:
    definitions: list[str]
    part_of_speech: str | None = None
    phonetic: str | None = None
    audio_url: str | None = None
    # Set only when the definitions belong to a different headword than the
    # looked-up form (e.g. "tailoring" -> "tailor"). Kept separate so the UI can
    # label it instead of silently playing the base word.
    base_word: str | None = None
    base_phonetic: str | None = None
    base_audio_url: str | None = None


@dataclass(frozen=True)
class EnrichedSentence:
    answer_zh: str
    definition_zh: str
    trans_zh: str
