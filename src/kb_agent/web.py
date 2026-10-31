"""Loopback-only acceptance UI over the same Agent executor as the CLI.

No credentials are read from files or persisted. A live request supplies its key
explicitly and passes it directly to LiveClient, never into AgentInput or Trace.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import threading
from typing import Literal
from urllib.parse import urlsplit
import uuid
import zipfile

from pydantic import Field, SecretStr, ValidationError

from .evaluation import assess
from .model import LiveClient, Settings
from .runner import run_agent, write_json
from .schema import AgentInput, Corpus, StrictModel


STATIC = Path(__file__).with_name("web_static")
CORPORA = {"no_conflict": "no_conflict.json", "conflict": "conflict.json", "replaced_45": "replaced_45.json"}
FILES = {"input.json", "output.json", "trace.jsonl", "meta.json", "review.json"}
JOB_ID = re.compile(r"^(mock|live)_[a-f0-9]{24}$")
NOTICE = "离线 Mock 只验证工程流程，不证明真实模型决策效果。"


class RunRequest(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list = Field(default_factory=list, max_length=20)
    mode: Literal["mock", "live"] = "mock"
    corpus: Literal["no_conflict", "conflict", "replaced_45"] = "no_conflict"
    corpus_data: dict | None = None
    fault: Literal["none", "first_search", "always_search"] = "none"
    mock_scenario: Literal["reimbursement", "outside", "endless"] = "reimbursement"
    max_steps: int = Field(default=12, ge=1, le=100)
    max_tool_calls: int = Field(default=10, ge=1, le=100)
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    run_timeout_seconds: int = Field(default=300, ge=1, le=3600)
    model: str = Field(default="deepseek-flash", min_length=1, max_length=128)
    api_key: SecretStr | None = None
    case_id: str | None = Field(default=None, max_length=16)


class Review(StrictModel):
    verdict: Literal["PASS", "FAIL", "NOT_RUN"]
    evidence_checked: bool
    notes: str = Field(default="", max_length=4000)


class WebApp:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.cases = json.loads((self.root / "data/evaluation_cases.json").read_text(encoding="utf-8"))["cases"]
        self.jobs = {}
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kb-ui")

    def public_cases(self):
        rows = []
        for case in self.cases:
            value = json.loads((self.root / case["input"]).read_text(encoding="utf-8"))
            rows.append({**case, **value, "corpus": Path(case["corpus"]).stem,
                         "fault": case.get("fault", "none"), "mock_scenario": case.get("mock_scenario", "reimbursement"),
                         "max_steps": case.get("budgets", {}).get("max_steps", 12),
                         "max_tool_calls": case.get("budgets", {}).get("max_tool_calls", 10)})
        return rows

    def job_root(self, job_id):
        match = JOB_ID.fullmatch(job_id)
        if not match:
            raise ValueError("无效运行标识")
        return self.root / "examples" / match.group(1) / "web" / job_id

    def matching_case(self, request):
        if request.case_id is None:
            return None
        for case in self.public_cases():
            keys = ("question", "history", "corpus", "fault", "mock_scenario", "max_steps", "max_tool_calls")
            if case["id"] == request.case_id and request.corpus_data is None and all(getattr(request, k) == case[k] for k in keys):
                if request.mode == "live" and case["id"] == "E08":
                    return None
                return next(c for c in self.cases if c["id"] == request.case_id)
        return None

    def start(self, payload):
        request = RunRequest.model_validate(payload)
        agent_input = AgentInput(question=request.question, history=request.history)
        if request.mode == "live" and (request.api_key is None or not request.api_key.get_secret_value().strip()):
            raise ValueError("请先输入 DeepSeek API Key")
        if request.api_key is not None and len(request.api_key.get_secret_value()) > 4096:
            raise ValueError("API Key 长度超出限制")
        if not request.model.strip():
            raise ValueError("模型名不能为空")
        corpus = Corpus.model_validate(request.corpus_data) if request.corpus_data is not None else None
        with self.lock:
            if sum(job["state"] in {"queued", "running"} for job in self.jobs.values()) >= 2:
                raise ValueError("已有两个任务正在执行，请等待完成后再试")
            job_id = request.mode + "_" + uuid.uuid4().hex[:24]
            directory = self.job_root(job_id)
            directory.mkdir(parents=True)
            # Whitelist persisted fields. api_key is intentionally absent.
            manifest = {"job_id": job_id, "created_at": datetime.now(timezone.utc).isoformat(),
                        "state": "queued", "mode": request.mode, "case_id": request.case_id,
                        "question": request.question, "corpus": request.corpus,
                        "custom_corpus": corpus is not None, "model": request.model if request.mode == "live" else "offline-scripted-mock-v1"}
            self.jobs[job_id] = manifest
            write_json(directory / "job.json", manifest)
            if corpus is not None:
                write_json(directory / "corpus.json", corpus.model_dump())
            # The original request/key only lives in this worker closure until completion.
            self.pool.submit(self._execute, job_id, request, agent_input, self.matching_case(request))
        return job_id

    def _execute(self, job_id, request, agent_input, case):
        directory = self.job_root(job_id)
        try:
            self.jobs[job_id]["state"] = "running"
            write_json(directory / "job.json", self.jobs[job_id])
            corpus_path = directory / "corpus.json" if request.corpus_data is not None else self.root / "data" / CORPORA[request.corpus]
            settings = Settings(max_steps=request.max_steps, max_tool_calls=request.max_tool_calls,
                                timeout_seconds=request.timeout_seconds, run_timeout_seconds=request.run_timeout_seconds)
            client = None
            if request.mode == "live":
                client = LiveClient(api_key=request.api_key.get_secret_value(), base_url="https://api.deepseek.com",
                                    model=request.model, provider="deepseek")
            result, run_dir = run_agent(agent_input, corpus_path, directory, mode=request.mode, settings=settings,
                                        fault=request.fault, mock_scenario=request.mock_scenario, client=client)
            check = None
            if case:
                errors = assess(case, result, run_dir)
                check = {"verdict": "FAIL" if errors else "PASS", "errors": errors,
                         "scope": "工程/有限自动断言，完整语义需人工复核"}
            self.jobs[job_id].update(state="completed", run_id=result.run_id, status=result.status, assessment=check)
        except Exception:
            # Credential/model/config exceptions must never echo user input values.
            self.jobs[job_id].update(state="failed", error="运行未完成，请核对模型配置或输入；未切换为 Mock。")
        finally:
            request.api_key = None
            write_json(directory / "job.json", self.jobs[job_id])

    def run_directory(self, job_id):
        directory = self.job_root(job_id)
        if not directory.is_dir():
            raise FileNotFoundError
        runs = [p for p in directory.iterdir() if p.is_dir() and (p / "input.json").is_file()]
        return runs[0] if runs else None

    def snapshot(self, job_id):
        root = self.job_root(job_id)
        if not (root / "job.json").is_file():
            raise FileNotFoundError
        with self.lock:
            job = dict(self.jobs.get(job_id) or json.loads((root / "job.json").read_text(encoding="utf-8")))
        run_dir = self.run_directory(job_id)
        result = {"job": job, "input": None, "output": None, "meta": None, "events": [], "review": None, "corpus_data": None}
        if run_dir:
            for filename, key in (("input.json", "input"), ("output.json", "output"), ("meta.json", "meta"), ("review.json", "review")):
                path = run_dir / filename
                if path.is_file():
                    try:
                        result[key] = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        pass  # Writer may be flushing the final file; the next poll sees it.
            path = run_dir / "trace.jsonl"
            if path.is_file():
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        result["events"].append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # Never invent a partially written event.
        corpus_path = root / "corpus.json" if job["custom_corpus"] else self.root / "data" / CORPORA[job["corpus"]]
        result["corpus_data"] = json.loads(corpus_path.read_text(encoding="utf-8"))
        return result

    def history(self):
        rows = []
        for mode in ("mock", "live"):
            folder = self.root / "examples" / mode / "web"
            if folder.exists():
                for path in folder.glob("*/job.json"):
                    try:
                        value = json.loads(path.read_text(encoding="utf-8"))
                        if JOB_ID.fullmatch(value["job_id"]):
                            rows.append(value)
                    except (ValueError, KeyError):
                        continue
        return sorted(rows, key=lambda x: x["created_at"], reverse=True)[:40]

    def archive(self, job_id):
        directory = self.run_directory(job_id)
        if directory is None or not (directory / "output.json").is_file():
            raise ValueError("任务完成后才能下载产物")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for filename in FILES:
                path = directory / filename
                if path.is_file():
                    archive.write(path, directory.name + "/" + filename)
            corpus_path = self.job_root(job_id) / "corpus.json"
            if corpus_path.is_file():
                archive.write(corpus_path, directory.name + "/corpus.json")
        return stream.getvalue()


def make_server(app, port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # No headers, bodies, credentials or user questions in access logs.

        def send(self, status, value, content_type="application/json; charset=utf-8", attachment=None):
            data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if attachment:
                self.send_header("Content-Disposition", 'attachment; filename="' + attachment + '"')
            self.end_headers()
            self.wfile.write(data)

        def allowed_origin(self):
            port = self.server.server_port
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            return self.headers.get("Host") in hosts and self.headers.get("Origin") in {None, *["http://" + h for h in hosts]}

        def do_GET(self):
            if not self.allowed_origin():
                self.send(403, {"error": "只允许本机同源访问"})
                return
            path = urlsplit(self.path).path
            try:
                assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
                if path in assets:
                    filename, mime = assets[path]
                    self.send(200, (STATIC / filename).read_bytes(), mime)
                elif path == "/api/config":
                    self.send(200, {"cases": app.public_cases(), "notice": NOTICE,
                                    "corpora": [{"id": name, "documents": len(json.loads((app.root / "data" / filename).read_text(encoding="utf-8"))["documents"])} for name, filename in CORPORA.items()],
                                    "known_gap": "数值和引文正确时，无依据的适用范围仍可能漏检，需人工语义复核。"})
                elif path == "/api/runs":
                    self.send(200, {"runs": app.history()})
                elif path.startswith("/api/corpus/") and path.rsplit("/", 1)[-1] in CORPORA:
                    self.send(200, json.loads((app.root / "data" / CORPORA[path.rsplit("/", 1)[-1]]).read_text(encoding="utf-8")))
                elif re.fullmatch(r"/api/runs/[^/]+", path):
                    self.send(200, app.snapshot(path.rsplit("/", 1)[-1]))
                elif re.fullmatch(r"/api/runs/[^/]+/download", path):
                    job_id = path.split("/")[3]
                    self.send(200, app.archive(job_id), "application/zip", job_id + ".zip")
                else:
                    self.send(404, {"error": "未找到资源"})
            except (ValueError, FileNotFoundError):
                self.send(404, {"error": "运行或文件不存在"})
            except Exception:
                self.send(500, {"error": "读取失败，请稍后重试"})

        def do_POST(self):
            authorized = (self.allowed_origin() and self.headers.get("X-KB-UI") == "1"
                          and self.headers.get("Content-Type", "").split(";")[0] == "application/json")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 256_000:
                    self.send(413, {"error": "请求为空或超过256KB"})
                    return
                # Drain a bounded request before closing even when unauthorized.
                # Closing over unread bytes can reset the TCP connection on
                # Windows, losing the 403 response. Never parse/execute a denied
                # request; bound both its size and time spent reading it.
                self.connection.settimeout(5)
                body = self.rfile.read(length)
                if not authorized:
                    self.send(403, {"error": "只允许本机页面的 JSON 请求"})
                    return
                payload = json.loads(body)
                path = urlsplit(self.path).path
                if path == "/api/runs":
                    self.send(202, {"job_id": app.start(payload)})
                elif re.fullmatch(r"/api/runs/[^/]+/review", path):
                    review = Review.model_validate(payload)
                    if review.verdict == "PASS" and not review.evidence_checked:
                        raise ValueError("标记通过前，请先确认已逐条核对原文与结论")
                    job_id = path.split("/")[3]
                    directory = app.run_directory(job_id)
                    if directory is None or not (directory / "output.json").is_file():
                        raise ValueError("请等待运行完成后再保存验收记录")
                    write_json(directory / "review.json", {**review.model_dump(), "reviewed_at": datetime.now(timezone.utc).isoformat()})
                    self.send(200, {"ok": True})
                else:
                    self.send(404, {"error": "未找到资源"})
            except ValidationError as exc:
                self.send(400, {"error": "输入不符合格式，请检查问题、历史、语料与参数",
                                "details": exc.errors(include_input=False, include_context=False, include_url=False)})
            except (ValueError, TypeError, FileNotFoundError):
                self.send(400, {"error": "输入无效，请核对API Key、JSON、执行预算或验收勾选项"})
            except Exception:
                self.send(500, {"error": "请求未完成，请稍后重试"})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(root: Path, port=8765):
    app = WebApp(root)
    server = make_server(app, port)
    print(f"本地验收页面：http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.pool.shutdown(wait=True)
