from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


class CollectWordRequest(BaseModel):
    word: str = Field(min_length=1, max_length=80)
    sentence: str = Field(min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2000)


class ReviewAnswerRequest(BaseModel):
    word: str = Field(min_length=1, max_length=80)
    correct: bool


@dataclass(frozen=True)
class DictEntry:
    definitions: list[str]
    part_of_speech: str | None = None
    phonetic: str | None = None
    audio_url: str | None = None


@dataclass(frozen=True)
class EnrichedSentence:
    answer_zh: str
    distractors: list[str]
    trans_zh: str
