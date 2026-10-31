import json

import pytest

from kb_agent.retrieval import KnowledgeBase, tokenize
from kb_agent.tools import ToolExecutor

from .conftest import ROOT


def test_conflict_candidates_both_returned(kb):
    hits = kb.search("报销材料 提交 期限", 6)
    assert {"D01", "D02"}.issubset({h["doc_id"] for h in hits})
    assert all(set(h) == {"doc_id", "section_id", "title", "version_date", "score", "preview"} for h in hits)


@pytest.mark.parametrize("query", ["", "  ", "!!!", "量子纠缠火星育儿假"])
def test_no_arbitrary_hits(kb, query):
    assert kb.search(query, 6) == []


def test_original_read_and_unknown_section(tools):
    result = tools.execute("read_excerpt", json.dumps({"doc_id": "D01", "section_id": "S01", "purpose": "核对原文"}))
    assert result["ok"] and result["error"] is None
    assert result["data"]["text"] == "报销材料须在费用发生后 30 天内提交。"
    assert result["data"]["scope"] is None and result["data"]["supersedes"] is None
    result["data"]["text"] = "caller mutation"
    assert tools.read_evidence[("D01", "S01")]["text"] != "caller mutation"
    missing = tools.execute("read_excerpt", json.dumps({"doc_id": "D01", "section_id": "missing", "purpose": "读取"}))
    assert missing["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("name,args,code", [
    ("search_documents", '{"query":" ","top_k":6,"purpose":"test"}', "INVALID_ARGUMENTS"),
    ("search_documents", '{"query":"报销","top_k":0,"purpose":"test"}', "INVALID_ARGUMENTS"),
    ("search_documents", '{"query":"报销","top_k":"6","purpose":"test"}', "INVALID_ARGUMENTS"),
    ("read_excerpt", '{"doc_id":"D01"}', "INVALID_ARGUMENTS"),
    ("search_documents", '[]', "INVALID_ARGUMENTS"),
    ("search_documents", 'not-json', "INVALID_ARGUMENTS"),
    ("delete_files", '{}', "UNKNOWN_TOOL"),
])
def test_structured_errors(tools, name, args, code):
    result = tools.execute(name, args)
    assert result["ok"] is False and result["data"] is None
    assert result["error"]["code"] == code
    assert isinstance(result["error"]["message"], str)
    assert isinstance(result["error"]["retryable"], bool)


@pytest.mark.parametrize("fault,expected", [("first_search", [False, True, True]), ("always_search", [False, False, False])])
def test_reproducible_faults(kb, fault, expected):
    executor = ToolExecutor(kb, fault)
    args = json.dumps({"query": "报销材料", "top_k": 6, "purpose": "test"})
    assert [executor.execute("search_documents", args)["ok"] for _ in range(3)] == expected
    assert executor.search_attempts == 3


def test_reload_content_no_cache():
    before = KnowledgeBase(ROOT / "data/no_conflict.json")
    after = KnowledgeBase(ROOT / "data/replaced_45.json")
    assert before.sha256 != after.sha256
    assert "30" in before.sections[("D01", "S01")]["text"]
    assert "45" in after.sections[("D01", "S01")]["text"]


def test_shared_normalization():
    assert tokenize("报账凭据递交") == tokenize("报销材料提交")
    assert tokenize("报账凭据递交", False) != tokenize("报销材料提交", False)


@pytest.mark.parametrize("doc_ids", [["D01"], ["D01", "D02"]])
def test_small_valid_corpus_does_not_lose_matching_documents(tmp_path, doc_ids):
    corpus = json.loads((ROOT / "data/conflict.json").read_text(encoding="utf-8"))
    corpus["documents"] = [d for d in corpus["documents"] if d["doc_id"] in doc_ids]
    path = tmp_path / "small.json"
    path.write_text(json.dumps(corpus, ensure_ascii=False), encoding="utf-8")
    hits = KnowledgeBase(path).search("报销材料 提交 期限", 6)
    assert set(doc_ids).issubset({h["doc_id"] for h in hits})
