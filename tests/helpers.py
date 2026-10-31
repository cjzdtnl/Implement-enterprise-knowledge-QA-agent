import copy
import json

from kb_agent.model import ModelReply


class ScriptClient:
    model_name = "test-script-fixture"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def complete(self, messages, tools, timeout):
        self.requests.append(copy.deepcopy(messages))
        reply = next(self.responses)
        if callable(reply):
            reply = reply(messages)
        return ModelReply(reply)


def call(name="search_documents", call_id="test_1", **kwargs):
    args = kwargs or {"query": "报销材料", "top_k": 6, "purpose": "测试检索"}
    return {"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function",
             "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]}


def run_id(messages):
    return messages[0]["content"].split("run_id 必须是 ")[1].split("。")[0]


def final(messages, **overrides):
    value = {"status": "insufficient_evidence", "answer": "测试知识库缺少依据。", "claims": [], "citations": [],
             "conflicts": [], "knowledge_gaps": ["缺少依据"], "clarification_question": None,
             "stop_reason": "test_completed", "run_id": run_id(messages)}
    value.update(overrides)
    return {"role": "assistant", "content": json.dumps(value, ensure_ascii=False)}


def answered(messages, quote="报销材料须在费用发生后 30 天内提交。", **overrides):
    value = {"status": "answered", "answer": quote,
             "claims": [{"text": quote, "citation_ids": ["C1"]}],
             "citations": [{"citation_id": "C1", "doc_id": "D01", "section_id": "S01",
                            "version_date": "2025-01-10", "quote": quote}], "knowledge_gaps": []}
    value.update(overrides)
    return final(messages, **value)
