"""EXPLICIT OFFLINE MOCK FIXTURE. Contains scripted business choices, never used in live.

离线 Mock 只验证工程流程，不证明真实模型决策效果。
This is intentionally not a general-purpose question-answering model.
"""
from __future__ import annotations

import json

from .model import ModelReply


class MockClient:
    model_name = "offline-scripted-mock-v1"

    def __init__(self, scenario="reimbursement"):
        if scenario not in {"reimbursement", "outside", "endless"}:
            raise ValueError("unknown mock scenario")
        self.scenario = scenario
        self.counter = 0

    def complete(self, messages, tools, timeout):
        self.counter += 1
        observations = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        run_id = messages[0]["content"].split("run_id 必须是 ")[1].split("。")[0]

        def call(name, **args):
            return ModelReply({"role": "assistant", "content": None, "tool_calls": [{
                "id": f"mock_call_{self.counter}", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
            }]})

        def search(query, purpose):
            return call("search_documents", query=query, top_k=6, purpose=purpose)

        def finish(status, answer, *, citations=None, claims=None, conflicts=None, gaps=None, question=None):
            return ModelReply({"role": "assistant", "content": json.dumps({
                "status": status, "answer": answer, "claims": claims or [], "citations": citations or [],
                "conflicts": conflicts or [], "knowledge_gaps": gaps or [],
                "clarification_question": question, "stop_reason": "mock_fixture_completed", "run_id": run_id,
            }, ensure_ascii=False)})

        if self.scenario == "endless":
            return search("报销", "Mock 预算测试：持续请求工具")
        query = "育儿假 天数" if self.scenario == "outside" else "报销材料 提交 期限"
        if not observations:
            return search(query, "Mock 脚本：检索制度候选（不代表真实模型选择）")
        errors = [o for o in observations if not o["ok"]]
        if not observations[-1]["ok"]:
            if len(errors) < 2 and observations[-1]["error"]["retryable"]:
                return search(query, "Mock 脚本：已观察到检索错误，有限重试一次")
            return finish("tool_failed", "检索服务持续失败，无法取得制度依据。", gaps=["缺少可用检索结果。"])
        if self.scenario == "outside":
            if len(observations) < 2:
                return search("育儿假 政策", "Mock 脚本：改写查询检查资料缺口")
            return finish("insufficient_evidence", "知识库没有育儿假政策，无法确定天数。", gaps=["缺少公司育儿假制度。"])
        candidates = {}
        reads = {}
        for o in observations:
            if not o["ok"]:
                continue
            data = o["data"]
            if "hits" in data:
                for hit in data["hits"]:
                    if "报销材料" in hit["title"]:
                        candidates[(hit["doc_id"], hit["section_id"])] = hit
            elif "text" in data:
                reads[(data["doc_id"], data["section_id"])] = data
        for key in candidates:
            if key not in reads:
                return call("read_excerpt", doc_id=key[0], section_id=key[1], purpose="Mock 脚本：读取候选制度原文")
        if not reads:
            return finish("insufficient_evidence", "未找到报销材料提交制度。", gaps=["缺少相关原文。"])
        values = list(reads.values())
        citations = [{"citation_id": f"C{i}", "doc_id": r["doc_id"], "section_id": r["section_id"],
                      "version_date": r["version_date"], "quote": r["text"]} for i, r in enumerate(values, 1)]
        claims = [{"text": r["text"], "citation_ids": [f"C{i}"]} for i, r in enumerate(values, 1)]
        if len({r["text"] for r in values}) > 1:
            previous_queries = [json.loads(c["function"]["arguments"]).get("query", "")
                                for m in messages for c in m.get("tool_calls", [])]
            if "报销 适用范围 替代关系 优先级" not in previous_queries:
                return search("报销 适用范围 替代关系 优先级", "Mock 脚本：已见不同制度，查找明示适用关系")
            return finish("needs_clarification", "资料对提交期限存在冲突：" + "；".join(r["text"] for r in values) + " 未说明适用范围或优先级，需确认适用制度。",
                          citations=citations, claims=claims,
                          conflicts=[{"issue": "报销材料提交期限", "sides": [
                              {"statement": c["text"], "citation_ids": c["citation_ids"]} for c in claims]}],
                          gaps=["缺少适用范围、明确替代关系或优先级说明。"],
                          question="请向制度负责人确认本次费用适用哪份报销制度？")
        return finish("answered", values[0]["text"], citations=citations, claims=claims)
