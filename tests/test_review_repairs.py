"""Independent regressions for gaps reproduced by review_acceptance.py."""
import json

import pytest

from kb_agent.evaluation import assess
from kb_agent.runner import run_agent
from kb_agent.schema import AgentInput, Citation
from kb_agent.validation import unsupported_quantities, validate_answer

from .conftest import ROOT
from .helpers import ScriptClient, final
from .test_validation import read_source, valid_value


@pytest.mark.parametrize("unsupported", ["30 年", "30 个月", "30 小时", "30 工作日", "30 自然日"])
def test_same_digits_cannot_justify_another_unit(tools, unsupported):
    read_source(tools)
    answer = valid_value()
    answer.answer = f"报销材料须在费用发生后 {unsupported}内提交。"
    answer.claims[0].text = answer.answer
    assert "UNSUPPORTED_QUANTITY" in {e["code"] for e in validate_answer(answer, tools, "unit")}


def test_quantity_screen_normalizes_width_and_optional_measure_word():
    source = Citation(citation_id="C1", doc_id="any", section_id="any", version_date="2025-01-01", quote="审批后 7 个工作日安排付款。")
    assert unsupported_quantities("审批后７工作日安排付款。", [source]) == []
    assert unsupported_quantities("审批后7天安排付款。", [source]) == ["7天"]


@pytest.mark.parametrize("fault,case_id", [("first_search", "E06"), ("always_search", "E07")])
def test_failure_status_without_executing_tool_is_not_acceptance_pass(tmp_path, fault, case_id):
    def fabricated_failure(messages):
        return final(messages, status="tool_failed", answer="检索失败，没有依据。", knowledge_gaps=["缺少依据"])
    result, directory = run_agent(AgentInput(question="报销材料最晚什么时候提交？"), ROOT / "data/no_conflict.json", tmp_path,
                                  mode="mock", client=ScriptClient([fabricated_failure]), fault=fault)
    case = next(c for c in json.loads((ROOT / "data/evaluation_cases.json").read_text(encoding="utf-8"))["cases"] if c["id"] == case_id)
    errors = assess(case, result, directory)
    assert "fault not observed" in errors
