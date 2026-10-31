"""Local UI API checks. DeepSeek responses are explicit offline HTTP fixtures."""
import io
import json
from pathlib import Path
import shutil
import socket
import threading
import time
import zipfile

import httpx
import pytest

from kb_agent.model import LiveClient
from kb_agent.web import WebApp, make_server

from .conftest import ROOT
from .helpers import answered, call


@pytest.fixture
def ui(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(ROOT / "data", root / "data")
    shutil.copytree(ROOT / "examples/inputs", root / "examples/inputs")
    app = WebApp(root)
    server = make_server(app, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False,
                      headers={"X-KB-UI": "1"}) as client:
        yield app, client, root
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
    app.pool.shutdown(wait=True)


def wait_for(client, job_id):
    until = time.monotonic() + 8
    while time.monotonic() < until:
        response = client.get("/api/runs/" + job_id)
        assert response.status_code == 200, response.text
        snapshot = response.json()
        if snapshot["job"]["state"] in {"completed", "failed"}:
            return snapshot
        time.sleep(.02)
    pytest.fail("local UI worker did not finish")


def start(client, **values):
    payload = {"question": "报销材料最晚什么时候提交？", "case_id": "E01", **values}
    response = client.post("/api/runs", json=payload)
    assert response.status_code == 202, response.text
    return wait_for(client, response.json()["job_id"])


def test_assets_and_synthetic_configuration(ui):
    _, client, _ = ui
    page = client.get("/")
    assert page.status_code == 200 and "验收工作台" in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert client.get("/app.js").status_code == 200
    assert client.get("/style.css").status_code == 200
    configuration = client.get("/api/config").json()
    assert len(configuration["cases"]) == 10 and "不证明真实模型" in configuration["notice"]
    assert client.get("/api/corpus/conflict").json()["synthetic"] is True
    assert client.get("/.env").status_code == 404
    assert client.get("/api/runs/not-a-run").status_code == 404


def test_normal_run_uses_shared_executor_and_downloads(ui, monkeypatch):
    app, client, root = ui
    def forbidden(*args, **kwargs):
        raise AssertionError("mock page must not create a live client")
    monkeypatch.setattr("kb_agent.web.LiveClient", forbidden)
    snapshot = start(client)
    assert snapshot["output"]["status"] == "answered"
    assert snapshot["output"]["citations"][0]["quote"] == "报销材料须在费用发生后 30 天内提交。"
    assert snapshot["job"]["assessment"]["verdict"] == "PASS"
    assert any(e["event"] == "model_request" and any(m["role"] == "tool" for m in e["messages"])
               for e in snapshot["events"])
    job_id = snapshot["job"]["job_id"]
    assert client.get("/api/runs").json()["runs"][0]["job_id"] == job_id
    archive = client.get("/api/runs/" + job_id + "/download")
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zip_file:
        assert {Path(name).name for name in zip_file.namelist()} == {"input.json", "output.json", "meta.json", "trace.jsonl"}


@pytest.mark.parametrize("case_id,values,status", [
    ("E02", {"corpus": "conflict"}, "needs_clarification"),
    ("E03", {"question": "公司育儿假有多少天？", "mock_scenario": "outside"}, "insufficient_evidence"),
    ("E06", {"fault": "first_search"}, "answered"),
    ("E07", {"fault": "always_search"}, "tool_failed"),
    ("E08", {"mock_scenario": "endless", "max_steps": 5, "max_tool_calls": 2}, "step_limit"),
])
def test_acceptance_modes_and_budgets(ui, case_id, values, status):
    _, client, _ = ui
    snapshot = start(client, case_id=case_id, **values)
    assert snapshot["output"]["status"] == status
    assert snapshot["job"]["assessment"]["verdict"] == "PASS"
    assert snapshot["meta"]["tool_calls"] <= snapshot["meta"]["config"]["max_tool_calls"]


def test_custom_corpus_is_a_per_run_copy(ui):
    app, client, root = ui
    corpus = client.get("/api/corpus/no_conflict").json()
    corpus["documents"][0]["sections"][0]["text"] = "报销材料须在费用发生后 47 天内提交。"
    snapshot = start(client, corpus_data=corpus)
    assert snapshot["output"]["answer"] == "报销材料须在费用发生后 47 天内提交。"
    assert snapshot["job"]["assessment"] is None
    assert "30" in (root / "data/no_conflict.json").read_text(encoding="utf-8")
    assert "47" in (app.job_root(snapshot["job"]["job_id"]) / "corpus.json").read_text(encoding="utf-8")


def test_live_key_is_used_but_never_persisted(ui, monkeypatch):
    app, client, root = ui
    calls = []
    secret = "UI_TEST_SECRET_NEVER_PERSIST"
    def transport(request):
        assert request.headers["authorization"] == "Bearer " + secret
        body = json.loads(request.content)
        assert body["thinking"] == {"type": "disabled"}
        calls.append(body)
        if len(calls) == 1:
            message = call(call_id="native-search")
        elif len(calls) == 2:
            assert body["messages"][-1]["role"] == "tool"
            message = call("read_excerpt", "native-read", doc_id="D01", section_id="S01", purpose="offline UI protocol fixture")
        else:
            message = answered(body["messages"])
        return httpx.Response(200, json={"choices": [{"message": message}]})
    def fake_provider(**kwargs):
        return LiveClient(**kwargs, transport=httpx.MockTransport(transport))
    monkeypatch.setattr("kb_agent.web.LiveClient", fake_provider)
    snapshot = start(client, mode="live", api_key=secret, model="configured-ui-test-model")
    assert snapshot["output"]["status"] == "answered" and len(calls) == 3
    assert snapshot["meta"]["mode"] == "live" and snapshot["meta"]["provider"] == "deepseek"
    assert secret not in json.dumps(snapshot)
    assert secret not in client.get("/api/runs").text
    for path in root.rglob("*"):
        if path.is_file():
            assert secret not in path.read_text(encoding="utf-8")
    archive = client.get("/api/runs/" + snapshot["job"]["job_id"] + "/download")
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zip_file:
        assert all(secret.encode() not in zip_file.read(name) for name in zip_file.namelist())


@pytest.mark.parametrize("change", [
    {"headers": {"Origin": "https://untrusted.invalid"}},
    {"headers": {"Host": "untrusted.invalid"}},
    {"headers": {"X-KB-UI": ""}},
])
def test_local_mutation_requires_same_origin(ui, change):
    _, client, _ = ui
    response = client.post("/api/runs", json={"question": "test"}, **change)
    assert response.status_code == 403


def test_rejected_bounded_body_is_consumed_before_closing(ui):
    _, client, _ = ui
    body = b'{"question":"test"}'
    headers = (f"POST /api/runs HTTP/1.0\r\nHost: 127.0.0.1:{client.base_url.port}\r\n"
               "Origin: https://untrusted.invalid\r\nContent-Type: application/json\r\n"
               f"Content-Length: {len(body)}\r\n\r\n").encode()
    with socket.create_connection(("127.0.0.1", client.base_url.port), timeout=2) as connection:
        connection.sendall(headers + body[:1])
        connection.settimeout(.1)
        with pytest.raises(socket.timeout):
            connection.recv(1)
        connection.sendall(body[1:])
        connection.settimeout(2)
        assert b"403" in connection.recv(1024).split(b"\r\n", 1)[0]
    assert client.get("/api/runs").json()["runs"] == []


def test_invalid_key_type_never_echoed(ui):
    _, client, _ = ui
    response = client.post("/api/runs", json={"question": "test", "mode": "live", "api_key": ["SECRET_INPUT_DO_NOT_ECHO"]})
    assert response.status_code == 400 and "SECRET_INPUT_DO_NOT_ECHO" not in response.text
    assert client.post("/api/runs", json={"question": "test", "mode": "live"}).status_code == 400


def test_review_is_separate_from_automatic_assertions(ui):
    app, client, _ = ui
    snapshot = start(client)
    path = "/api/runs/" + snapshot["job"]["job_id"] + "/review"
    assert client.post(path, json={"verdict": "PASS", "evidence_checked": False, "notes": ""}).status_code == 400
    assert client.post(path, json={"verdict": "PASS", "evidence_checked": True, "notes": "EXPLICIT TEST FIXTURE review"}).status_code == 200
    updated = client.get("/api/runs/" + snapshot["job"]["job_id"]).json()
    assert updated["review"]["evidence_checked"] is True
    assert updated["review"]["verdict"] == "PASS"
    assert updated["job"]["assessment"]["verdict"] == "PASS"
