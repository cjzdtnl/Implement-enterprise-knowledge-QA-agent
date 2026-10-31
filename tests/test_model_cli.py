import json
import os
import subprocess
import sys

import httpx
import pytest

from kb_agent.model import ConfigurationError, LiveClient, ModelError
from kb_agent.runner import run_agent
from kb_agent.schema import AgentInput

from .conftest import ROOT


def test_native_api_request_and_no_reasoning_leak():
    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "configured-test-model" and body["tool_choice"] == "auto"
        return httpx.Response(200, headers={"x-request-id": "request-fixture"}, json={
            "choices": [{"message": {"role": "assistant", "content": None, "reasoning_content": "hidden",
                "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "search_documents", "arguments": "{}"}}]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })
    client = LiveClient(api_key="test-key", base_url="https://example.invalid/v1", model="configured-test-model", transport=httpx.MockTransport(handler))
    reply = client.complete([{"role": "user", "content": "test"}], [], 1)
    assert reply.request_id == "request-fixture" and reply.usage["prompt_tokens"] == 10
    assert "reasoning_content" not in reply.message


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_failure_no_retry_or_secret(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"x-request-id": "error-request-fixture"}, text="server echoes SECRET_API_KEY")
    client = LiveClient(api_key="SECRET_API_KEY", base_url="https://example.invalid/v1", model="fixture", transport=httpx.MockTransport(handler))
    with pytest.raises(ModelError) as error:
        client.complete([], [], 1)
    assert len(calls) == 1 and "SECRET_API_KEY" not in str(error.value)
    assert error.value.request_id == "error-request-fixture"
    assert error.value.latency_ms is not None


@pytest.mark.parametrize("base", ["https://secret:password@example.invalid/v1", "https://example.invalid/v1?key=secret", "http://example.invalid/v1"])
def test_reject_unsafe_config_url(base):
    with pytest.raises(ConfigurationError):
        LiveClient(api_key="test", base_url=base, model="fixture")


def test_missing_key_live_saves_failure_not_mock(tmp_path, monkeypatch):
    for key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    result, directory = run_agent(AgentInput(question="报销材料最晚什么时候提交？"), ROOT / "data/no_conflict.json", tmp_path, mode="live")
    assert result.status == "model_error" and result.stop_reason == "CONFIG_MISSING"
    meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    assert meta["mode"] == "live" and meta["model"] is None and meta["steps"] == 0
    assert not any(e.get("event") == "action" for e in map(json.loads, (directory / "trace.jsonl").read_text(encoding="utf-8").splitlines()))


def test_installed_cli_from_outside_repository(tmp_path):
    result = subprocess.run([sys.executable, "-m", "kb_agent", "run", "--mode", "mock", "--input", str(ROOT / "examples/inputs/normal.json"),
                             "--corpus", str(ROOT / "data/no_conflict.json"), "--output-dir", str(tmp_path / "runs")], cwd=tmp_path,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["result"]["status"] == "answered"
    assert "离线 Mock" in result.stderr


@pytest.mark.live
def test_live_opt_in(tmp_path):
    if os.getenv("KB_AGENT_RUN_LIVE_TESTS") != "1":
        pytest.skip("显式设置 KB_AGENT_RUN_LIVE_TESTS=1 才调用真实模型；批量验收用 evaluate --mode live")
    result, _ = run_agent(AgentInput(question="报销材料最晚什么时候提交？"), ROOT / "data/no_conflict.json", tmp_path, mode="live")
    assert result.status == "answered"
