from __future__ import annotations

import json
from typing import Literal

from pydantic import ValidationError

from .retrieval import KnowledgeBase
from .schema import ReadArgs, SearchArgs


def failure(code: str, message: str, retryable: bool = False) -> dict:
    return {"ok": False, "data": None, "error": {
        "code": code, "message": message, "retryable": retryable,
    }}


def success(data: dict) -> dict:
    return {"ok": True, "data": data, "error": None}


class ToolExecutor:
    def __init__(self, kb: KnowledgeBase, fault: Literal["none", "first_search", "always_search"] = "none"):
        self.kb = kb
        self.fault = fault
        self.search_attempts = 0
        self.read_evidence: dict[tuple[str, str], dict] = {}

    def execute(self, name: str, arguments: str) -> dict:
        try:
            raw = json.loads(arguments)
            if name == "search_documents":
                args = SearchArgs.model_validate(raw)
                if not args.query.strip():
                    return failure("INVALID_ARGUMENTS", "query must not be blank")
                self.search_attempts += 1
                if self.fault == "always_search" or (self.fault == "first_search" and self.search_attempts == 1):
                    return failure("SEARCH_UNAVAILABLE", "合成故障注入：检索暂不可用", True)
                return success({"hits": self.kb.search(args.query, args.top_k)})
            if name == "read_excerpt":
                args = ReadArgs.model_validate(raw)
                row = self.kb.sections.get((args.doc_id, args.section_id))
                if row is None:
                    return failure("NOT_FOUND", "文档或章节不存在", False)
                self.read_evidence[(args.doc_id, args.section_id)] = row.copy()
                return success(row.copy())
            return failure("UNKNOWN_TOOL", "工具不在允许列表中")
        except (ValueError, TypeError, ValidationError):
            return failure("INVALID_ARGUMENTS", "参数必须符合工具 JSON schema")
        except Exception:
            # Do not return raw exceptions that could contain credentials/paths.
            return failure("TOOL_INTERNAL_ERROR", "工具执行异常", True)
