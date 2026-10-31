"""All HTTP responses in this file are fixtures, not live model evidence."""
import copy
import json
import os
import subprocess
import sys

import httpx
import pytest

from kb_agent.config import load_env_file
from kb_agent.model import ConfigurationError, LiveClient, ModelError, Settings
from kb_agent.runner import run_agent
from kb_agent.schema import AgentInput, tool_definitions

from .conftest import ROOT
from .helpers import answered


def test_deepseek_defaults_and_key_alias(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-secret")
    client = LiveClient(provider="deepseek")
    assert client.model_name == "deepseek-flash"
    assert client.base_url == "https://api.deepseek.com"
    assert client.public_config() == {"provider": "deepseek", "base_url": "https://api.deepseek.com",
                                      "thinking": "disabled", "server_strict_tools": False}
    assert "fixture-secret" not in json.dumps(client.public_config())


def test_deepseek_requires_key():
    with pytest.raises(ConfigurationError, match="LLM_API_KEY") as error:
        LiveClient(provider="deepseek")
    assert "LLM_MODEL" not in str(error.value)


def test_deepseek_request_and_feedback_roundtrip(tmp_path):
    requests = []
    definitions = tool_definitions()
    original_definitions = copy.deepcopy(definitions)

    def handler(request):
        body = json.loads(request.content)
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert body["model"] == "deepseek-flash"
        assert body["thinking"] == {"type": "disabled"}
        assert all("strict" not in t["function"] for t in body["tools"])
        assert "reasoning_content" not in json.dumps(body)
        requests.append(body)
        messages = body["messages"]
        if len(requests) == 1:
            message = {"role": "assistant", "content": "", "tool_calls": [{
                "id": "ds_test_search", "type": "function", "function": {"name": "search_documents", "arguments": json.dumps({
                    "query": "报销材料 提交", "top_k": 6, "purpose": "离线协议测试：检索"}, ensure_ascii=False)},
            }]}
        elif len(requests) == 2:
            assert messages[-1]["role"] == "tool" and messages[-1]["tool_call_id"] == "ds_test_search"
            assert json.loads(messages[-1]["content"])["data"]["hits"][0]["doc_id"] == "D01"
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "ds_test_read", "type": "function", "function": {"name": "read_excerpt", "arguments": json.dumps({
                    "doc_id": "D01", "section_id": "S01", "purpose": "离线协议测试：核对原文"}, ensure_ascii=False)},
            }]}
        else:
            assert messages[-1]["role"] == "tool" and messages[-1]["tool_call_id"] == "ds_test_read"
            assert json.loads(messages[-1]["content"])["data"]["text"] == "报销材料须在费用发生后 30 天内提交。"
            assert json.loads(messages[1]["content"])["untrusted_input"]["history"][0]["content"] == "费用报销"
            message = answered(messages)
        return httpx.Response(200, headers={"x-request-id": f"fixture-{len(requests)}"}, json={
            "choices": [{"finish_reason": "tool_calls" if message.get("tool_calls") else "stop", "message": message}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8},
        })

    client = LiveClient(api_key="DO_NOT_PERSIST_TEST_SECRET", provider="deepseek", transport=httpx.MockTransport(handler))
    result, directory = run_agent(AgentInput(question="那最晚多久交？", history=[{"role": "user", "content": "费用报销"}]),
                                  ROOT / "data/no_conflict.json", tmp_path, mode="mock", client=client)
    assert result.status == "answered" and len(requests) == 3
    assert definitions == original_definitions
    meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    assert meta["provider"] == "deepseek" and meta["thinking"] == "disabled"
    assert meta["model_requests"][-1]["request_id"] == "fixture-3"
    assert all("DO_NOT_PERSIST_TEST_SECRET" not in path.read_text(encoding="utf-8") for path in directory.iterdir())
    assert all("reasoning_content" not in path.read_text(encoding="utf-8") for path in directory.iterdir())


def test_adapter_does_not_mutate_shared_tools():
    definitions = tool_definitions()
    original = copy.deepcopy(definitions)
    client = LiveClient(api_key="fixture", provider="deepseek", transport=httpx.MockTransport(lambda _: httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": "{}"}}]})))
    client.complete([], definitions, 1)
    assert definitions == original
    assert all(t["function"]["strict"] is True for t in definitions)


def test_unexpected_reasoning_is_not_saved(tmp_path):
    client = LiveClient(api_key="fixture", provider="deepseek", transport=httpx.MockTransport(lambda _: httpx.Response(
        200, json={"choices": [{"message": {"role": "assistant", "content": "{}", "reasoning_content": "DO_NOT_STORE_HIDDEN_REASONING"}}]})))
    result, directory = run_agent(AgentInput(question="报销材料？"), ROOT / "data/no_conflict.json", tmp_path, mode="mock", client=client)
    assert result.status == "model_error" and result.stop_reason == "UNEXPECTED_REASONING_MODE"
    assert all("DO_NOT_STORE_HIDDEN_REASONING" not in path.read_text(encoding="utf-8") for path in directory.iterdir())


def test_explicit_config_load_precedence_and_no_execution(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text('# comment\nexport LLM_PROVIDER=deepseek\nLLM_API_KEY="literal$(NEVER_EXECUTE)#token"\nLLM_MODEL=from-file\n', encoding="utf-8-sig")
    monkeypatch.setenv("LLM_MODEL", "process-wins")
    assert load_env_file(path) == ["LLM_API_KEY", "LLM_MODEL", "LLM_PROVIDER"]
    assert os.environ["LLM_API_KEY"] == "literal$(NEVER_EXECUTE)#token"
    assert os.environ["LLM_MODEL"] == "process-wins"


@pytest.mark.parametrize("invalid", ["unknown=SECRET", "LLM_API_KEY", 'LLM_API_KEY="SECRET', "LLM_API_KEY=", "LLM_API_KEY=SECRET\nLLM_API_KEY=SECRET"])
def test_config_error_never_echoes_secret(tmp_path, invalid):
    path = tmp_path / ".env"
    path.write_text("LLM_PROVIDER=deepseek\n" + invalid + "\n", encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_env_file(path)
    assert "SECRET" not in str(error.value)
    assert "LLM_PROVIDER" not in os.environ  # atomic load


def test_cli_deepseek_config_without_network(tmp_path):
    config = tmp_path / ".env"
    config.write_text("LLM_PROVIDER=deepseek\nLLM_API_KEY=OFFLINE_CONFIG_FIXTURE\n", encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "kb_agent", "run", "--mode", "mock", "--provider", "deepseek", "--env-file", str(config),
                             "--input", str(ROOT / "examples/inputs/normal.json"), "--corpus", str(ROOT / "data/no_conflict.json"),
                             "--output-dir", str(tmp_path / "runs")], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["result"]["status"] == "answered"
    assert "OFFLINE_CONFIG_FIXTURE" not in result.stdout + result.stderr


def test_invalid_budget_value_is_not_echoed(monkeypatch):
    monkeypatch.setenv("MAX_STEPS", "ACCIDENTAL_SECRET_VALUE")
    with pytest.raises(ValueError) as error:
        Settings.from_env()
    assert "ACCIDENTAL_SECRET_VALUE" not in str(error.value)


@pytest.mark.parametrize("reason", ["length", "content_filter", "insufficient_system_resource", "aborted"])
def test_incomplete_provider_response_cannot_be_accepted(reason):
    client = LiveClient(api_key="fixture", provider="deepseek", transport=httpx.MockTransport(lambda _: httpx.Response(
        200, headers={"x-request-id": "interrupted-fixture"}, json={"choices": [{"finish_reason": reason,
            "message": {"role": "assistant", "content": "{}"}}]})))
    with pytest.raises(ModelError) as error:
        client.complete([], [], 1)
    assert error.value.code == "INCOMPLETE_MODEL_RESPONSE"
    assert error.value.request_id == "interrupted-fixture"
