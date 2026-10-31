"""Evaluation expectations live here/data, never in the production decision loop."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .model import Settings
from .retrieval import KnowledgeBase
from .runner import run_agent, utc_now, write_json
from .schema import AgentInput, FinalAnswer
from .validation import numeric_support_errors


def load_events(directory: Path) -> list[dict]:
    return [json.loads(line) for line in (directory / "trace.jsonl").read_text(encoding="utf-8").splitlines()]


def assess(case: dict, result: FinalAnswer, directory: Path) -> list[str]:
    """Small transparent checks, not a complete semantic entailment judge."""
    errors = []

    def require(condition, description):
        if not condition:
            errors.append(description)

    require(result.status in case["statuses"], f"expected status in {case['statuses']}, got {result.status}")
    citations = {c.citation_id: c for c in result.citations}
    docs = {c.doc_id for c in result.citations}
    require(set(case.get("expected_docs", [])).issubset(docs), "missing required source documents")
    for number in case.get("expected_numbers", []):
        require(re.search(rf"(?<!\d){number}(?!\d)", result.answer) is not None, f"answer missing number {number}")
        require(any(re.search(rf"(?<!\d){number}(?!\d)", c.quote) for c in result.citations), f"quote missing number {number}")
    # Check claim-to-citation numeric agreement separately from substring validity.
    for claim in result.claims:
        quotes = " ".join(citations[c].quote for c in claim.citation_ids if c in citations)
        require(set(re.findall(r"\d+", claim.text)).issubset(set(re.findall(r"\d+", quotes))), "claim has unsupported number")
    errors.extend(e["message"] for e in numeric_support_errors(result))
    if case.get("expected_numbers") and result.status == "answered":
        require("费用发生后" in result.answer.replace(" ", ""), "answer lost expense-event time condition")
        require("报销材料" in result.answer, "answer changed policy object")
        require(not result.conflicts, "unexpected unresolved conflict")
    if case.get("conflict"):
        require(bool(result.conflicts) and bool(result.clarification_question) and bool(result.knowledge_gaps), "missing conflict/gap/question")
        side_docs = {citations[c].doc_id for conflict in result.conflicts for side in conflict.sides
                     for c in side.citation_ids if c in citations}
        require({"D01", "D02"}.issubset(side_docs), "conflict sides lack both sources")
        require(not re.search(r"保险起见|按\s*15\s*天执行|新版本优先", result.answer), "unjustified precedence advice")
    if result.status in {"tool_failed", "insufficient_evidence"}:
        require(not result.claims, "failure/outside case fabricated policy claims")
        require(bool(result.knowledge_gaps), "missing knowledge gap")
    events = load_events(directory)
    reads = {e["result"]["data"]["doc_id"] for e in events if e["event"] == "tool_result"
             and e["tool_name"] == "read_excerpt" and e["result"]["ok"]}
    require(set(case.get("expected_docs", [])).issubset(reads), "required source was not actually read")
    if case.get("conflict"):
        read_steps = [e["step"] for e in events if e["event"] == "tool_result" and e["tool_name"] == "read_excerpt" and e["result"]["ok"]]
        scope_searches = [e for e in events if e["event"] == "tool_call" and e["tool_name"] == "search_documents"
                          and any(term in str(e["arguments"].get("query", "")) for term in ("适用", "范围", "替代", "优先", "覆盖"))]
        require(bool(read_steps) and any(e["step"] > max(read_steps) for e in scope_searches), "no follow-up search for explicit precedence after reading")
    if case.get("fault") in {"first_search", "always_search"}:
        search_results = [e for e in events if e["event"] == "tool_result" and e["tool_name"] == "search_documents"]
        failures = [e for e in search_results if not e["result"]["ok"] and e["result"]["error"]["code"] == "SEARCH_UNAVAILABLE"]
        require(bool(failures), "fault not observed")
        if failures:
            failure = failures[0]
            requests = [e for e in events if e["event"] == "model_request" and e["step"] > failure["step"]]
            if requests:
                require(any(m.get("tool_call_id") == failure["tool_call_id"] and json.loads(m["content"]) == failure["result"]
                            for m in requests[0]["messages"] if m["role"] == "tool"), "error observation missing from next model request")
            # A one-step budget may end immediately after the failed call.
            # Otherwise a completed failure scenario must show the model saw it.
            if result.status != "step_limit":
                require(bool(requests), "no model request after tool failure")
                require(any(e["event"] == "action" and e["step"] > failure["step"] for e in events), "no actual model action after failure")
            if case["fault"] == "first_search":
                require(any(e["result"]["ok"] and e["step"] > failure["step"] for e in search_results), "temporary failure did not recover through a later model action")
        if case["fault"] == "always_search":
            require(not any(e["result"]["ok"] for e in search_results), "persistent search fault unexpectedly succeeded")
    meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    require(meta["steps"] <= meta["config"]["max_steps"], "step budget exceeded")
    require(meta["tool_calls"] <= meta["config"]["max_tool_calls"], "tool budget exceeded")
    if case.get("id") == "E08":
        require(result.stop_reason == "max_tool_calls" and meta["tool_calls"] == 2, "incorrect budget termination")
    return errors


def evaluate_cases(mode: str, output_dir: Path | None = None) -> int:
    root = output_dir or Path("examples") / mode
    case_path = Path("data/evaluation_cases.json")
    cases = json.loads(case_path.read_text(encoding="utf-8"))["cases"]
    # Unique evaluation folder preserves even failed/rerun summaries.
    import uuid
    evaluation_dir = root / ("evaluation_" + utc_now().replace(":", "").replace(".", "_") + "_" + uuid.uuid4().hex[:6])
    evaluation_dir.mkdir(parents=True)
    report = {"mode": mode, "started_at": utc_now(), "expectations_sha256": hashlib.sha256(case_path.read_bytes()).hexdigest(),
              "notice": "离线 Mock 只验证工程流程，不证明真实模型决策效果。" if mode == "mock" else "真实模型评估，配置失败不降级为 Mock。",
              "cases": []}
    for case in cases:
        if mode == "live" and case["id"] == "E08":
            report["cases"].append({"id": "E08", "verdict": "NOT_RUN", "reason": "该用例为 Mock 持续工具请求的执行器预算测试"})
            continue
        value = AgentInput.model_validate_json(Path(case["input"]).read_text(encoding="utf-8"))
        settings = Settings.from_env(**case.get("budgets", {}))
        result, directory = run_agent(value, Path(case["corpus"]), evaluation_dir / case["id"], mode=mode,
                                      settings=settings, fault=case.get("fault", "none"), mock_scenario=case.get("mock_scenario", "reimbursement"))
        if result.stop_reason == "CONFIG_MISSING":
            verdict, errors = "BLOCKED", [result.answer]
        else:
            errors = assess(case, result, directory)
            verdict = "FAIL" if errors else "PASS"
        report["cases"].append({"id": case["id"], "name": case["name"], "verdict": verdict, "status": result.status,
                                "run_id": result.run_id, "directory": directory.as_posix(), "checks_failed": errors,
                                "semantic_review": "数字/对象/条件等有限自动检查；完整语义支持待人工复核"})
    report["ended_at"] = utc_now()
    report["counts"] = {v: sum(c["verdict"] == v for c in report["cases"]) for v in ("PASS", "FAIL", "BLOCKED", "NOT_RUN")}
    path = evaluation_dir / "report.json"
    write_json(path, report)
    print(json.dumps({"report": path.as_posix(), "counts": report["counts"], "notice": report["notice"]}, ensure_ascii=False, indent=2))
    return 0 if all(c["verdict"] == "PASS" for c in report["cases"]) else 2


def evaluate_retrieval(corpus_path: Path, queries_path: Path, output_root: Path) -> int:
    import uuid
    raw = queries_path.read_bytes()
    queries = json.loads(raw.decode("utf-8"))
    directory = output_root / ("comparison_" + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True)
    report = {"started_at": utc_now(), "queries_sha256": hashlib.sha256(raw).hexdigest(),
              "k": queries["k"], "definition": "Recall@k=召回相关文档数/标签相关文档数；完整召回率=全部标签文档均入选的查询比例；不是回答准确率。", "versions": {}}
    for name, normalize in (("before", False), ("after", True)):
        kb = KnowledgeBase(corpus_path, normalize)
        report["corpus_sha256"] = kb.sha256
        rows = []
        for q in queries["queries"]:
            hits = kb.search(q["query"], queries["k"])
            found = {r["doc_id"] for r in hits}
            relevant = set(q["relevant_doc_ids"])
            rows.append({**q, "hits": hits, "recall_at_k": len(found & relevant) / len(relevant),
                         "complete_recall": relevant.issubset(found),
                         "conflict_both_recalled": {"D01", "D02"}.issubset(found) if {"D01", "D02"}.issubset(relevant) else None})
        summary = {}
        for split in ("all", "dev", "heldout"):
            selected = [r for r in rows if split == "all" or r["split"] == split]
            conflicts = [r for r in selected if r["conflict_both_recalled"] is not None]
            summary[split] = {"query_count": len(selected), "mean_recall_at_k": sum(r["recall_at_k"] for r in selected) / len(selected),
                              "complete_recall_rate": sum(r["complete_recall"] for r in selected) / len(selected),
                              "conflict_both_rate": sum(r["conflict_both_recalled"] for r in conflicts) / len(conflicts) if conflicts else None}
        report["versions"][name] = {"rows": rows, "summary": summary}
    report["ended_at"] = utc_now()
    write_json(directory / "report.json", report)
    print(json.dumps({"report": (directory / "report.json").as_posix(), "summary": {n: v["summary"] for n, v in report["versions"].items()}}, ensure_ascii=False, indent=2))
    return 0
