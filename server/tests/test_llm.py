import pytest

from app.services.llm import LLMError, _parse_enriched


def test_parse_enriched_accepts_card_translations():
    result = _parse_enriched(
        {
            "answer_zh": "容易处理的",
            "definition_zh": "容易处理或解决的",
            "trans_zh": "这个问题是容易处理的。",
        }
    )

    assert result.answer_zh == "容易处理的"
    assert result.definition_zh == "容易处理或解决的"
    assert result.trans_zh == "这个问题是容易处理的。"


@pytest.mark.parametrize("missing", ["answer_zh", "definition_zh", "trans_zh"])
def test_parse_enriched_rejects_missing_card_translation(missing):
    payload = {
        "answer_zh": "容易处理的",
        "definition_zh": "容易处理或解决的",
        "trans_zh": "这个问题是容易处理的。",
    }
    payload[missing] = ""

    with pytest.raises(LLMError, match="missing"):
        _parse_enriched(payload)
