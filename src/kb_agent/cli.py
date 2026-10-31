from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from .model import Settings
from .config import load_env_file
from .runner import run_agent
from .schema import AgentInput


def main(argv=None):
    # Stable UTF-8 output when invoked from Windows PowerShell or redirected to files.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="企业知识问答 Agent（合成资料 CLI）")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--mode", choices=["mock", "live"], required=True)
    run.add_argument("--input", type=Path, required=True)
    run.add_argument("--corpus", type=Path, default=Path("data/no_conflict.json"))
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--fault", choices=["none", "first_search", "always_search"], default="none")
    run.add_argument("--mock-scenario", choices=["reimbursement", "outside", "endless"], default="reimbursement")
    run.add_argument("--max-steps", type=int)
    run.add_argument("--max-tool-calls", type=int)
    run.add_argument("--timeout-seconds", type=float)
    run.add_argument("--run-timeout-seconds", type=float)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--mode", choices=["mock", "live"], required=True)
    evaluate.add_argument("--output-dir", type=Path)
    for command in (run, evaluate):
        command.add_argument("--provider", choices=["generic", "deepseek"], help="模型服务适配；DeepSeek 显式关闭思考，使用标准原生 tools")
        command.add_argument("--env-file", type=Path, help="显式读取本机配置；进程环境变量优先；不会自动加载 .env")
    retrieval = sub.add_parser("retrieval-eval")
    retrieval.add_argument("--corpus", type=Path, default=Path("data/conflict.json"))
    retrieval.add_argument("--queries", type=Path, default=Path("data/retrieval_queries.json"))
    retrieval.add_argument("--output-dir", type=Path, default=Path("examples/retrieval"))
    web = sub.add_parser("serve", help="启动本机可视化验收页面")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            from .web import serve
            if not 0 <= args.port <= 65535:
                parser.error("port 必须为0..65535")
            serve(args.project_root, args.port)
            return 0
        if getattr(args, "env_file", None) is not None:
            load_env_file(args.env_file)
        if getattr(args, "provider", None) is not None:
            os.environ["LLM_PROVIDER"] = args.provider
        if args.command == "evaluate":
            from .evaluation import evaluate_cases
            return evaluate_cases(args.mode, args.output_dir)
        if args.command == "retrieval-eval":
            from .evaluation import evaluate_retrieval
            return evaluate_retrieval(args.corpus, args.queries, args.output_dir)
        if args.mode == "live" and args.mock_scenario != "reimbursement":
            parser.error("--mock-scenario 只能用于 mock 模式")
        settings = Settings.from_env(max_steps=args.max_steps, max_tool_calls=args.max_tool_calls,
                                     timeout_seconds=args.timeout_seconds, run_timeout_seconds=args.run_timeout_seconds)
        value = AgentInput.model_validate_json(args.input.read_text(encoding="utf-8-sig"))
        result, directory = run_agent(value, args.corpus, args.output_dir, mode=args.mode,
                                      settings=settings, fault=args.fault, mock_scenario=args.mock_scenario)
        if args.mode == "mock":
            print("离线 Mock 只验证工程流程，不证明真实模型决策效果。", file=sys.stderr)
        print(json.dumps({"output_dir": str(directory), "result": result.model_dump()}, ensure_ascii=False, indent=2))
        return 0 if result.status in {"answered", "needs_clarification", "insufficient_evidence"} else 2
    except (OSError, ValueError, ValidationError) as exc:
        print(json.dumps({"error": "INVALID_INPUT_OR_CONFIGURATION", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
