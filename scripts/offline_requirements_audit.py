"""Independent offline negative probes; all model messages are explicit test fixtures.

No environment file is read. LiveClient.complete is disabled during all probes.
Wrong answers are intentional adversarial fixtures, never actual model evidence.
"""
from __future__ import annotations

import ast
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid
from unittest.mock import patch

from kb_agent.evaluation import assess, load_events
from kb_agent.mock import MockClient
from kb_agent.model import LiveClient, ModelReply
from kb_agent.retrieval import KnowledgeBase, tokenize
from kb_agent.runner import run_agent, write_json
from kb_agent.schema import AgentInput
from kb_agent.tools import ToolExecutor


ROOT = Path(__file__).resolve().parents[1]


class MutatingMock(MockClient):
    """Purposefully wrong output fixture, used only by this offline audit."""
    model_name = "offline-audit-adversarial-fixture"

    def __init__(self, mutation, once=False):
        super().__init__()
        self.mutation, self.once, self.mutations = mutation, once, 0

    def complete(self, messages, tools, timeout):
        reply = super().complete(messages, tools, timeout)
        if not reply.message.get("tool_calls"):
            value = json.loads(reply.message["content"])
            if not self.once or self.mutations == 0:
                self.mutation(value)
                self.mutations += 1
            return ModelReply({"role": "assistant", "content": json.dumps(value, ensure_ascii=False)})
        return reply


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    started = datetime.now(timezone.utc).isoformat()
    directory = ROOT / "examples/audit" / ("requirements_" + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True)
    cases = {c["id"]: c for c in json.loads((ROOT / "data/evaluation_cases.json").read_text(encoding="utf-8"))["cases"]}
    normal = AgentInput.model_validate_json((ROOT / "examples/inputs/normal.json").read_text(encoding="utf-8"))
    probes = []

    def execute(identifier, base_case, mutate, once=False):
        fixture = MutatingMock(mutate, once)
        result, run_dir = run_agent(normal, ROOT / base_case["corpus"], directory / identifier, mode="mock",
                                    client=fixture, mock_scenario="explicit_offline_audit_" + identifier)
        evaluation_errors = assess(base_case, result, run_dir)
        events = load_events(run_dir)
        validation_codes = [e["code"] for event in events if event["event"] == "validation_error"
                            for e in event.get("errors", []) if isinstance(e, dict)]
        return result, run_dir, evaluation_errors, validation_codes

    def record(identifier, name, passed, expected, observed, *, run_dir=None, priority=None, note=None):
        probes.append({"id": identifier, "name": name, "verdict": "PASS" if passed else "FAIL",
                       "expected": expected, "observed": observed,
                       "directory": run_dir.relative_to(ROOT).as_posix() if run_dir else None,
                       "priority": priority, "note": note,
                       "fixture_notice": "离线构造的错误模型输出，不是实际模型错误或真实决策证据。"})

    with patch.object(LiveClient, "complete", side_effect=AssertionError("OFFLINE_AUDIT_FORBIDS_LIVE_REQUESTS")) as forbidden:
        def wrong_extra_number(value):
            value["answer"] += " 另外，所有员工实际也可以在 99 天内提交报销材料。"
        result, run_dir, errors, codes = execute("A01", cases["E01"], wrong_extra_number)
        record("A01", "正确引文/claim 之外夹带无依据的99天", bool(errors), "独立评估拒绝错误回答中的额外数字",
               {"status": result.status, "answer": result.answer, "evaluation_errors": errors, "runtime_validation_codes": codes},
               run_dir=run_dir, priority="P1", note="检查正确claim之外的answer数值，不允许用正确引文掩盖额外制度数字。")

        def swapped_conflict(value):
            sides = value["conflicts"][0]["sides"]
            sides[0]["citation_ids"], sides[1]["citation_ids"] = sides[1]["citation_ids"], sides[0]["citation_ids"]
        result, run_dir, errors, codes = execute("A02", cases["E02"], swapped_conflict)
        record("A02", "冲突双方的引用ID串位", bool(errors), "独立评估拒绝30天引用15天原文/15天引用30天原文",
               {"status": result.status, "conflicts": [c.model_dump() for c in result.conflicts],
                "evaluation_errors": errors, "runtime_validation_codes": codes},
               run_dir=run_dir, priority="P1", note="有双方来源不代表各方表述与所引原文匹配。")

        result, run_dir, errors, codes = execute("A03", cases["E01"], lambda v: v.update(answer="   "))
        record("A03", "空白回答不能标记answered", result.status != "answered", "执行器拒绝仅空白的成功回答",
               {"status": result.status, "answer": result.answer, "evaluation_errors": errors, "runtime_validation_codes": codes},
               run_dir=run_dir, priority="P1", note="评估拒绝不足以替代执行器对空白成功回答的拦截。")

        full = json.loads((ROOT / "data/conflict.json").read_text(encoding="utf-8"))
        minimal = {**full, "documents": [d for d in full["documents"] if d["doc_id"] in {"D01", "D02"}]}
        fixture_dir = directory / "fixtures"
        fixture_dir.mkdir()
        minimal_path = fixture_dir / "minimal_conflict.json"
        write_json(minimal_path, minimal)
        kb = KnowledgeBase(minimal_path)
        hits = kb.search("报销材料 提交 期限", 6)
        found = {h["doc_id"] for h in hits}
        record("A04", "合法两文档语料的检索边界", {"D01", "D02"}.issubset(found), "能够召回两份确实包含查询词的制度",
               {"hits": hits, "corpus_sha256": kb.sha256, "fixture": minimal_path.relative_to(ROOT).as_posix(),
                "raw_bm25_scores": [float(s) for s in kb.index.get_scores(tokenize("报销材料 提交 期限"))]},
               priority="P2", note="默认9/10篇之外的合法小语料边界；负/零分不能直接视为不匹配。")

        def unsupported_scope(value):
            extra = " 本制度仅限上海办公室正式员工，实习生不能适用。"
            value["answer"] += extra
            value["claims"][0]["text"] += extra
        result, run_dir, errors, codes = execute("A05", cases["E01"], unsupported_scope)
        record("A05", "无原文依据的范围/对象限制", bool(errors), "数字正确但新增无依据范围时需要被语义复核拒绝",
               {"status": result.status, "answer": result.answer, "evaluation_errors": errors, "runtime_validation_codes": codes},
               run_dir=run_dir, priority="P1", note="这属于已声明的完整语义校验限制，不能靠字符串匹配完全解决；当前缺少必做人工审阅记录。")

        invalid_variants = [
            ("A06", "错版本引用反馈后修复", "SOURCE_MISMATCH", lambda v: v["citations"][0].update(version_date="2099-01-01")),
            ("A07", "改写/错误原文反馈后修复", "QUOTE_MISMATCH", lambda v: v["citations"][0].update(quote="费用后45天以内报账。")),
            ("A08", "未读取的文档引用被拦截", "SOURCE_NOT_READ", lambda v: v["citations"][0].update(doc_id="D04", version_date="2025-02-10", quote="账号密码至少包含 12 个字符。")),
            ("A09", "不存在的claim引用ID被拦截", "UNKNOWN_CITATION", lambda v: v["claims"][0].update(citation_ids=["C404"])),
        ]
        for identifier, name, expected_code, mutation in invalid_variants:
            result, run_dir, errors, codes = execute(identifier, cases["E01"], mutation, once=True)
            passed = expected_code in codes and result.status == "answered" and not errors
            record(identifier, name, passed, f"先出现 {expected_code}，随后修复为有依据的正常答案",
                   {"status": result.status, "evaluation_errors": errors, "runtime_validation_codes": codes}, run_dir=run_dir)

        kb = KnowledgeBase(ROOT / "data/no_conflict.json")
        tools = ToolExecutor(kb)
        search = tools.execute("search_documents", json.dumps({"query": "产品客服 在线服务时间", "top_k": 6, "purpose": "离线审查产品FAQ检索"}, ensure_ascii=False))
        hit = next((h for h in search["data"]["hits"] if h["doc_id"] == "D10"), None)
        read = tools.execute("read_excerpt", json.dumps({"doc_id": hit["doc_id"], "section_id": hit["section_id"], "purpose": "离线审查产品FAQ原文"}, ensure_ascii=False)) if hit else None
        passed = bool(read and read["ok"] and "09:00" in read["data"]["text"] and "18:00" in read["data"]["text"])
        record("A10", "报销之外的产品FAQ检索/读取", passed, "产品客服文档能检索并准确读取服务时间",
               {"search_result": search, "read_result": read}, note="只验证工具，未证明真实模型理解产品FAQ。")

        outside_hits = kb.search("公司育儿假有多少天", 6)
        module_names = ("model", "runner", "retrieval", "tools", "schema", "validation", "prompt", "cli", "config")
        fixed_ids = []
        for module in module_names:
            path = ROOT / "src/kb_agent" / (module + ".py")
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in {"D01", "D02", "E01", "E02", "E09", "E10"}:
                    fixed_ids.append({"file": path.relative_to(ROOT).as_posix(), "line": node.lineno, "literal": node.value})
        record("A11", "生产决策模块不按固定文档/用例ID路由", not fixed_ids, "关键执行/传输/检索模块没有固定D01/D02或验收编号分支",
               {"fixed_id_literals": fixed_ids}, note="AST 字面量检查仅作代码审查辅助；Mock 和评估预期中的ID明确允许。")
        live_calls = forbidden.call_count

    report = {"started_at": started, "ended_at": datetime.now(timezone.utc).isoformat(),
              "mode": "offline_audit", "live_model_requests": live_calls,
              "implementation_sha256": {name: hashlib.sha256((ROOT / "src/kb_agent" / (name + ".py")).read_bytes()).hexdigest()
                                        for name in ("runner", "retrieval", "validation", "evaluation")},
              "notice": "离线 Mock 只验证工程流程，不证明真实模型决策效果。错误答案是特意构造的负例。",
              "probes": probes, "counts": {verdict: sum(p["verdict"] == verdict for p in probes) for verdict in ("PASS", "FAIL")},
              "observations": {"outside_question": "公司育儿假有多少天", "outside_lexical_hits": outside_hits,
                               "outside_interpretation": "这些词面候选不提供育儿假依据，模型应过滤；本轮未验证模型是否正确处理。"}}
    write_json(directory / "report.json", report)
    print(json.dumps({"report": (directory / "report.json").relative_to(ROOT).as_posix(), "counts": report["counts"],
                      "live_model_requests": live_calls,
                      "failures": [{"id": p["id"], "name": p["name"], "priority": p["priority"]} for p in probes if p["verdict"] == "FAIL"]}, ensure_ascii=False, indent=2))
    return 1 if report["counts"]["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
