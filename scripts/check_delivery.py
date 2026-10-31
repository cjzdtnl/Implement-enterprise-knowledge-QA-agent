"""Read-only checks of committed-eligible sources and actual run artifacts."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from kb_agent.retrieval import KnowledgeBase
from kb_agent.schema import FinalAnswer
from kb_agent.tools import ToolExecutor
from kb_agent.validation import validate_answer


root = Path(__file__).resolve().parents[1]
errors = []
intentional_negative_outputs = []
kb_by_hash = {}
corpus_paths = [*(root / "data").glob("*.json"),
                *root.glob("examples/audit/**/fixtures/*.json"),
                *root.glob("examples/*/web/*/corpus.json")]
for path in corpus_paths:
    if "documents" not in json.loads(path.read_text(encoding="utf-8")):
        continue
    kb = KnowledgeBase(path)
    kb_by_hash[kb.sha256] = kb
count = 0
for trace in (root / "examples").rglob("trace.jsonl"):
    count += 1
    directory = trace.parent
    meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    final = FinalAnswer.model_validate_json((directory / "output.json").read_text(encoding="utf-8"))
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    if meta["corpus_sha256"] not in kb_by_hash:
        errors.append(f"{trace.relative_to(root)}: corpus snapshot for hash is missing")
        continue
    tools = ToolExecutor(kb_by_hash[meta["corpus_sha256"]])
    observations = {}
    for event in events:
        assert event["run_id"] == meta["run_id"] == final.run_id
        assert event["mode"] == meta["mode"]
        if event["event"] == "tool_result":
            observations[event["tool_call_id"]] = event["result"]
            if event["tool_name"] == "read_excerpt" and event["result"]["ok"]:
                row = event["result"]["data"]
                key = (row["doc_id"], row["section_id"])
                assert row == tools.kb.sections[key]
                tools.read_evidence[key] = row
        if event["event"] == "model_request":
            context = {m["tool_call_id"]: json.loads(m["content"]) for m in event["messages"] if m["role"] == "tool"}
            assert all(context.get(key) == value for key, value in observations.items())
    validation_errors = validate_answer(final, tools, meta["run_id"])
    if meta["mode"] == "mock" and meta["model"] == "offline-audit-adversarial-fixture" and validation_errors:
        # These are deliberately wrong audit outputs, retained to demonstrate
        # pre-fix bugs. Report them separately; never count them as business PASS.
        intentional_negative_outputs.append({"trace": trace.relative_to(root).as_posix(), "validation_errors": validation_errors})
    else:
        errors.extend(f"{trace.relative_to(root)}: {error}" for error in validation_errors)
    assert meta["tool_calls"] == sum(e["event"] == "tool_call" for e in events)
    assert meta["steps"] == sum(e["event"] == "model_request" for e in events)
    assert meta["tool_calls"] <= meta["config"]["max_tool_calls"]
    assert meta["steps"] <= meta["config"]["max_steps"]
    assert events[-1]["event"] == "final" and events[-1]["output"] == final.model_dump()

files = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root).decode("utf-8").split("\0")
for name in filter(None, files):
    path = root / name
    assert not any(part in {".venv", "__pycache__", "work", ".pytest_cache"} for part in path.relative_to(root).parts)
    assert path.name != ".env"
    if path.suffix == ".md":
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#")[0]
            if not (path.parent / target).exists():
                errors.append(f"broken link: {name} -> {target}")
    if path.suffix in {".py", ".md", ".toml"}:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.rstrip() != line:
                errors.append(f"trailing whitespace: {name}:{number}")
print(json.dumps({"run_artifacts_checked": count, "eligible_files": len([f for f in files if f]),
                  "errors": errors, "intentional_negative_outputs": intentional_negative_outputs,
                  "notice": "只校验工程证据一致性；故意错误的审查fixture单独列出，不计作业务通过。"}, ensure_ascii=False, indent=2))
raise SystemExit(1 if errors else 0)
