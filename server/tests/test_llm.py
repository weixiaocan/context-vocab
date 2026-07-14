import pytest

from app.services.llm import LLMError, _parse_enriched


def test_parse_enriched_rejects_near_synonym_distractors():
    with pytest.raises(LLMError):
        _parse_enriched(
            {
                "answer_zh": "严谨的",
                "distractors": ["严密的", "苛刻的", "精确的"],
                "trans_zh": "我们学会了如何设计更严谨、更有用的评估。",
            }
        )


def test_parse_enriched_accepts_discriminative_distractors():
    result = _parse_enriched(
        {
            "answer_zh": "严谨的",
            "distractors": ["苛刻的", "僵硬的", "猛烈的"],
            "trans_zh": "我们学会了如何设计更严谨、更有用的评估。",
        }
    )

    assert result.answer_zh == "严谨的"
