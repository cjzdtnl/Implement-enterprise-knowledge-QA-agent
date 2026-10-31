from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from .model import LiveClient, ModelClient, ModelError, Settings
from .prompt import system_prompt
from .retrieval import KnowledgeBase
from .schema import AgentInput, Citation, FinalAnswer, tool_definitions
from .tools import ToolExecutor
from .validation import validate_answer


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Trace:
    def __init__(self, path: Path, run_id: str, mode: str):
        self.path, self.run_id, self.mode = path, run_id, mode

    def emit(self, event: str, step: int, **payload):
        record = {"timestamp": utc_now(), "run_id": self.run_id, "mode": self.mode,
                  "event": event, "step": step, "status": "running", **payload}
        # Written and flushed at the time of the event, never reconstructed later.
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()


def incomplete(status: str, reason: str, run_id: str, tools: ToolExecutor, message: str) -> FinalAnswer:
    citations = [Citation(citation_id=f"retained_{i}", doc_id=row["doc_id"],
                          section_id=row["section_id"], version_date=row["version_date"], quote=row["text"])
                 for i, row in enumerate(tools.read_evidence.values(), 1)]
    return FinalAnswer(status=status, answer=message, claims=[], citations=citations, conflicts=[],
                       knowledge_gaps=["任务未完成；已读取证据予以保留，尚不能据此确定答案。"],
                       clarification_question=None, stop_reason=reason, run_id=run_id)


def run_agent(
    agent_input: AgentInput, corpus_path: Path, output_root: Path, *, mode: str,
    settings: Settings | None = None, fault: str = "none", client: ModelClient | None = None,
    mock_scenario: str = "reimbursement", normalize: bool = True,
) -> tuple[FinalAnswer, Path]:
    if mode not in {"mock", "live"}:
        raise ValueError("mode must be mock or live")
    settings = settings or Settings()
    # Preflight input/corpus errors do not create misleading partial run folders.
    kb = KnowledgeBase(corpus_path, normalize=normalize)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:12]
    directory = output_root / run_id
    directory.mkdir(parents=True, exist_ok=False)
    trace = Trace(directory / "trace.jsonl", run_id, mode)
    started_at, started = utc_now(), time.perf_counter()
    write_json(directory / "input.json", agent_input.model_dump())
    tools = ToolExecutor(kb, fault=fault)
    meta = {
        "run_id": run_id, "mode": mode, "started_at": started_at, "ended_at": None,
        "duration_seconds": None, "model": None, "api_style": "chat_completions_native_tools",
        "config": asdict(settings), "corpus_file": corpus_path.name, "corpus_sha256": kb.sha256,
        "retrieval": "bm25_bigrams_normalized" if normalize else "bm25_bigrams_baseline",
        "fault_injection": {"mode": fault}, "transport_retries": 0,
        "mock_scenario": mock_scenario if mode == "mock" else None,
        "notice": "离线 Mock 只验证工程流程，不证明真实模型决策效果。" if mode == "mock" else None,
        "steps": 0, "tool_calls": 0, "model_requests": [], "error": None,
    }
    write_json(directory / "meta.json", meta)
    trace.emit("run_started", 0, corpus_sha256=kb.sha256, fault_injection=fault)
    steps, count = 0, 0
    result = None
    try:
        if client is None:
            if mode == "live":
                client = LiveClient()
            else:
                from .mock import MockClient
                client = MockClient(mock_scenario)
        meta["model"] = client.model_name
        if isinstance(client, LiveClient):
            meta.update(client.public_config())
        messages = [
            {"role": "system", "content": system_prompt(run_id, settings.max_steps, settings.max_tool_calls)},
            # One user data envelope prevents past assistant text from becoming a new instruction.
            {"role": "user", "content": json.dumps({"untrusted_input": agent_input.model_dump()}, ensure_ascii=False)},
        ]
        seen_call_ids = set()
        for step in range(1, settings.max_steps + 1):
            remaining = settings.run_timeout_seconds - (time.perf_counter() - started)
            if remaining <= 0:
                result = incomplete("step_limit", "run_timeout", run_id, tools, "运行时间预算耗尽，任务未完成。")
                break
            steps = step
            # Exact visible context: proves tool results were included in the next request.
            trace.emit("model_request", step, messages=messages, remaining_tool_calls=settings.max_tool_calls - count)
            try:
                reply = client.complete(messages, tool_definitions(), min(settings.timeout_seconds, remaining))
            except ModelError as exc:
                meta["model_requests"].append({"step": step, "request_id": exc.request_id, "usage": None,
                                               "latency_ms": exc.latency_ms, "error_code": exc.code})
                raise
            meta["model_requests"].append({"step": step, "request_id": reply.request_id,
                                           "usage": reply.usage, "latency_ms": reply.latency_ms})
            message = reply.message
            calls = message.get("tool_calls") if isinstance(message, dict) else None
            valid = isinstance(message, dict) and message.get("role") == "assistant"
            if calls is not None:
                valid = valid and isinstance(calls, list) and bool(calls) and len(calls) <= 100
                if valid:
                    current_ids = []
                    for call in calls:
                        valid = valid and isinstance(call, dict) and call.get("type") == "function"
                        if not valid:
                            break
                        fn = call.get("function")
                        valid = isinstance(fn, dict) and isinstance(fn.get("name"), str) and isinstance(fn.get("arguments"), str)
                        valid = valid and isinstance(call.get("id"), str) and bool(call["id"])
                        if not valid:
                            break
                        current_ids.append(call["id"])
                    valid = valid and len(current_ids) == len(set(current_ids)) and not seen_call_ids.intersection(current_ids)
            if not valid:
                error = {"ok": False, "error": {"code": "INVALID_ACTION", "message": "工具动作格式错误或 call_id 重复", "retryable": True}}
                trace.emit("validation_error", step, errors=error)
                messages.append({"role": "user", "content": json.dumps({"executor_feedback": error}, ensure_ascii=False)})
                continue
            # Whitelist visible fields; no hidden reasoning or provider-specific extras in files.
            clean = {"role": "assistant", "content": message.get("content")}
            if calls:
                clean["tool_calls"] = [{"id": c["id"], "type": "function", "function": {
                    "name": c["function"]["name"], "arguments": c["function"]["arguments"],
                }} for c in calls]
            trace.emit("action", step, action=clean)
            messages.append(clean)
            if time.perf_counter() - started >= settings.run_timeout_seconds:
                result = incomplete("step_limit", "run_timeout", run_id, tools, "运行时间预算耗尽，任务未完成。")
                break
            if calls:
                for call in clean["tool_calls"]:
                    if count >= settings.max_tool_calls:
                        trace.emit("tool_skipped", step, tool_call_id=call["id"], reason="max_tool_calls")
                        result = incomplete("step_limit", "max_tool_calls", run_id, tools, "工具调用预算耗尽，任务未完成。")
                        break
                    if time.perf_counter() - started >= settings.run_timeout_seconds:
                        result = incomplete("step_limit", "run_timeout", run_id, tools, "运行时间预算耗尽，任务未完成。")
                        break
                    count += 1
                    seen_call_ids.add(call["id"])
                    fn = call["function"]
                    try:
                        arguments = json.loads(fn["arguments"])
                    except (ValueError, TypeError):
                        arguments = {"invalid_json": True}
                    purpose = arguments.get("purpose") if isinstance(arguments, dict) else None
                    trace.emit("tool_call", step, tool_call_id=call["id"], tool_name=fn["name"],
                               arguments=arguments, decision_summary=purpose, tool_calls_used=count)
                    observation = tools.execute(fn["name"], fn["arguments"])
                    trace.emit("tool_result", step, tool_call_id=call["id"], tool_name=fn["name"], result=observation)
                    messages.append({"role": "tool", "tool_call_id": call["id"],
                                     "content": json.dumps(observation, ensure_ascii=False)})
                if result is not None:
                    break
                continue
            try:
                candidate = FinalAnswer.model_validate_json(clean.get("content") or "")
                errors = validate_answer(candidate, tools, run_id)
            except (ValidationError, ValueError, TypeError):
                errors = [{"code": "INVALID_FINAL_SCHEMA", "message": "最终输出必须符合系统给出的 JSON schema"}]
            if not errors:
                result = candidate
                break
            trace.emit("validation_error", step, errors=errors)
            messages.append({"role": "user", "content": json.dumps({
                "executor_feedback": {"ok": False, "error": {"code": "FINAL_VALIDATION_FAILED", "message": errors, "retryable": True}},
                "instruction": "修复输出或补充读取后再次提交。不得伪造原文。",
            }, ensure_ascii=False)})
        if result is None:
            result = incomplete("step_limit", "max_steps", run_id, tools, "模型请求预算耗尽，任务未完成。")
    except ModelError as exc:
        meta["error"] = {"code": exc.code, "message": str(exc)}
        trace.emit("model_error", steps, error=meta["error"])
        result = incomplete("model_error", exc.code, run_id, tools, str(exc))
    except Exception as exc:
        # Keep evidence on unexpected failure; report type only to avoid leaking secrets.
        meta["error"] = {"code": "EXECUTOR_ERROR", "exception_type": type(exc).__name__}
        trace.emit("executor_error", steps, error=meta["error"])
        result = incomplete("model_error", "EXECUTOR_ERROR", run_id, tools, "执行器异常，任务未完成；请检查记录。")
    meta.update(ended_at=utc_now(), duration_seconds=round(time.perf_counter() - started, 6),
                steps=steps, tool_calls=count, status=result.status, stop_reason=result.stop_reason)
    trace.emit("final", steps, status=result.status, stop_reason=result.stop_reason,
               tool_calls_used=count, output=result.model_dump())
    write_json(directory / "output.json", result.model_dump())
    write_json(directory / "meta.json", meta)
    return result, directory
