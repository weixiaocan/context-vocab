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


@pytest.mark.parametrize(
    ("answer", "distractors"),
    [
        ("微小的", ["微不足道的", "可忽略的", "极少的"]),
        ("过早地", ["仓促地", "轻率地", "草率地"]),
        ("部分的", ["偏袒的", "不完整的", "局部的"]),
        ("警告", ["提示", "通知", "确认"]),
    ],
)
def test_parse_enriched_rejects_observed_near_synonym_piles(answer, distractors):
    with pytest.raises(LLMError, match="near-synonyms"):
        _parse_enriched(
            {
                "answer_zh": answer,
                "distractors": distractors,
                "trans_zh": "示例译文。",
            }
        )


def test_parse_enriched_rejects_duplicate_options():
    with pytest.raises(LLMError, match="unique"):
        _parse_enriched(
            {
                "answer_zh": "足够",
                "distractors": ["存在", "足够", "生效"],
                "trans_zh": "更简单的设置就足够了。",
            }
        )
