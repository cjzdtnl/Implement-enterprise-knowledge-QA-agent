"""Capture actual subprocess outputs and exit codes without overwriting older runs."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone


def build_commands(*, offline_only=False, provider=None, env_file=None):
    commands = [
        ("pip-check", ["-m", "pip", "check"]),
        ("offline-tests", ["-m", "pytest", "-q", "-m", "not live", "--tb=short"]),
        ("mock-evaluation", ["-m", "kb_agent", "evaluate", "--mode", "mock"]),
    ]
    if not offline_only:
        options = []
        if provider:
            options += ["--provider", provider]
        if env_file is not None:
            options += ["--env-file", str(env_file.resolve())]
        commands.append(("live-evaluation", ["-m", "kb_agent", "evaluate", "--mode", "live", *options]))
    commands.append(("retrieval-evaluation", ["-m", "kb_agent", "retrieval-eval"]))
    return commands


def run_checks(root, commands):
    directory = root / "examples" / "verification" / ("session_" + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    records = []
    for name, arguments in commands:
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        result = subprocess.run([sys.executable, *arguments], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8")
        (directory / f"{name}.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (directory / f"{name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        records.append({"name": name, "command": ["python", *arguments], "started_at": started_at,
                        "ended_at": datetime.now(timezone.utc).isoformat(), "exit_code": result.returncode,
                        "duration_seconds": round(time.perf_counter() - started, 6)})
        print(f"{name}: exit={result.returncode}")
        print(result.stdout[:4000])
    (directory / "commands.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(directory.relative_to(root).as_posix())
    # Failed tests/checks must fail a CI job; business incompletion remains code 2.
    if any(r["exit_code"] != 0 and r["name"] != "live-evaluation" for r in records):
        return 1, directory
    return (2 if any(r["exit_code"] != 0 for r in records) else 0), directory


def main(argv=None):
    parser = argparse.ArgumentParser(description="采集测试与评估的实际结果")
    parser.add_argument("--provider", choices=["generic", "deepseek"])
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--offline-only", action="store_true", help="只运行离线测试/Mock/检索评估，不调用 live 或读取密钥文件")
    args = parser.parse_args(argv)
    code, _ = run_checks(Path(__file__).resolve().parents[1], build_commands(
        offline_only=args.offline_only, provider=args.provider, env_file=args.env_file))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
