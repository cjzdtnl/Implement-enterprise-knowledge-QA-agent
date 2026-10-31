import json

import pytest

from kb_agent.schema import FinalAnswer
from kb_agent.validation import validate_answer

from .helpers import answered


def valid_value():
    return FinalAnswer.model_validate_json(answered([{"content": "run_id 必须是 unit。"}])["content"])


def read_source(tools):
    tools.execute("read_excerpt", json.dumps({"doc_id": "D01", "section_id": "S01", "purpose": "test"}))


def test_cannot_cite_unread_search_preview(tools):
    tools.execute("search_documents", json.dumps({"query": "报销材料", "top_k": 6, "purpose": "test"}))
    assert "SOURCE_NOT_READ" in {e["code"] for e in validate_answer(valid_value(), tools, "unit")}


def test_exact_citation_passes(tools):
    read_source(tools)
    assert validate_answer(valid_value(), tools, "unit") == []


@pytest.mark.parametrize("field,value,code", [
    ("doc_id", "D404", "SOURCE_MISMATCH"),
    ("section_id", "S404", "SOURCE_MISMATCH"),
    ("version_date", "2099-01-01", "SOURCE_MISMATCH"),
    ("quote", "报销材料需在30天内提交。", "QUOTE_MISMATCH"),
    ("quote", "报销材料须在费用发生后 45 天内提交。", "QUOTE_MISMATCH"),
])
def test_bad_citation_rejected(tools, field, value, code):
    read_source(tools)
    answer = valid_value()
    setattr(answer.citations[0], field, value)
    assert code in {e["code"] for e in validate_answer(answer, tools, "unit")}


def test_missing_claim_reference_and_unattributed_answer(tools):
    read_source(tools)
    answer = valid_value()
    answer.claims[0].citation_ids = ["missing"]
    assert "UNKNOWN_CITATION" in {e["code"] for e in validate_answer(answer, tools, "unit")}
    answer.claims = []
    assert "ANSWER_WITHOUT_EVIDENCE" in {e["code"] for e in validate_answer(answer, tools, "unit")}


def test_run_and_duplicate_ids(tools):
    read_source(tools)
    answer = valid_value()
    answer.citations.append(answer.citations[0].model_copy())
    assert {"RUN_ID_MISMATCH", "DUPLICATE_CITATION"}.issubset({e["code"] for e in validate_answer(answer, tools, "different")})


def test_extra_unsupported_number_in_answer_is_rejected(tools):
    read_source(tools)
    answer = valid_value()
    answer.answer += " 所有员工也可以在 99 天内提交。"
    assert "UNSUPPORTED_NUMBER" in {e["code"] for e in validate_answer(answer, tools, "unit")}


def test_number_must_match_its_claim_citation(tools):
    read_source(tools)
    answer = valid_value()
    answer.claims[0].text = "费用发生后 99 天内提交报销材料。"
    assert "UNSUPPORTED_NUMBER" in {e["code"] for e in validate_answer(answer, tools, "unit")}


def test_citation_metadata_does_not_supply_policy_quantities(tools):
    read_source(tools)
    answer = valid_value()
    answer.answer = "根据 D01（2025-01-10），报销材料须在费用发生后 30 天内提交。"
    assert validate_answer(answer, tools, "unit") == []
    answer.answer += " 实际也可在 2025 天内提交。"
    assert "UNSUPPORTED_NUMBER" in {e["code"] for e in validate_answer(answer, tools, "unit")}


def test_empty_success_answer_is_rejected(tools):
    read_source(tools)
    answer = valid_value()
    answer.answer = " \n\t"
    assert "EMPTY_ANSWER" in {e["code"] for e in validate_answer(answer, tools, "unit")}
