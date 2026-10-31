from __future__ import annotations

import json
import copy
import os
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx


class ModelError(Exception):
    def __init__(self, code: str, message: str, *, request_id=None, latency_ms=None):
        self.code = code
        self.request_id = request_id
        self.latency_ms = latency_ms
        super().__init__(message)


class ConfigurationError(ModelError):
    pass


@dataclass
class ModelReply:
    # Only visible action/final content is retained; hidden reasoning is discarded.
    message: dict
    request_id: str | None = None
    usage: dict | None = None
    latency_ms: float | None = None


class ModelClient(Protocol):
    model_name: str

    def complete(self, messages: list[dict], tools: list[dict], timeout: float) -> ModelReply: ...


@dataclass
class Settings:
    max_steps: int = 12
    max_tool_calls: int = 10
    timeout_seconds: float = 30
    run_timeout_seconds: float = 180

    def __post_init__(self):
        if not (1 <= self.max_steps <= 100 and 1 <= self.max_tool_calls <= 100):
            raise ValueError("budgets must be within 1..100")
        if not (0 < self.timeout_seconds <= 600 and 0 < self.run_timeout_seconds <= 3600):
            raise ValueError("timeouts out of range")

    @classmethod
    def from_env(cls, **overrides):
        try:
            values = {
                "max_steps": int(os.getenv("MAX_STEPS", "12")),
                "max_tool_calls": int(os.getenv("MAX_TOOL_CALLS", "10")),
                "timeout_seconds": float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
                "run_timeout_seconds": float(os.getenv("RUN_TIMEOUT_SECONDS", "180")),
            }
        except ValueError:
            raise ValueError("执行预算或超时环境变量格式错误（不显示取值）") from None
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)


class LiveClient:
    """Native Chat Completions tools over HTTP. No SDK/transport retries, no fallback."""

    def __init__(self, *, api_key=None, base_url=None, model=None, transport=None, provider=None):
        self.provider = provider if provider is not None else os.getenv("LLM_PROVIDER", "generic")
        if self.provider not in {"generic", "deepseek"}:
            raise ConfigurationError("INVALID_PROVIDER", "LLM_PROVIDER 必须为 generic 或 deepseek")
        is_deepseek = self.provider == "deepseek"
        key = api_key if api_key is not None else os.getenv("LLM_API_KEY", "")
        if api_key is None and not key and is_deepseek:
            key = os.getenv("DEEPSEEK_API_KEY", "")
        # Model and endpoint defaults verified against official docs on 2026-10-30.
        # Environment/explicit arguments always permit selecting another available model.
        base = base_url if base_url is not None else os.getenv("LLM_BASE_URL", "https://api.deepseek.com" if is_deepseek else "")
        self.model_name = model if model is not None else os.getenv("LLM_MODEL", "deepseek-flash" if is_deepseek else "")
        missing = [name for name, value in [("LLM_API_KEY", key), ("LLM_BASE_URL", base), ("LLM_MODEL", self.model_name)] if not value.strip()]
        if missing:
            raise ConfigurationError("CONFIG_MISSING", "缺少环境变量：" + ", ".join(missing))
        parsed = urlsplit(base)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ConfigurationError("INVALID_BASE_URL", "BASE_URL 不得包含凭据、查询参数或 fragment")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
            raise ConfigurationError("INVALID_BASE_URL", "使用 HTTPS；仅本地调试允许 HTTP")
        self.base_url = base.rstrip("/")
        self._key = key
        self._transport = transport

    def public_config(self) -> dict:
        return {"provider": self.provider, "base_url": self.base_url,
                "thinking": "disabled" if self.provider == "deepseek" else None,
                "server_strict_tools": self.provider != "deepseek"}

    def complete(self, messages, tools, timeout):
        started = time.perf_counter()
        response = None
        try:
            payload = {"model": self.model_name, "messages": messages,
                       "tools": copy.deepcopy(tools), "tool_choice": "auto"}
            if self.provider == "deepseek":
                # Standard endpoint, not the beta strict endpoint. Local Pydantic
                # validation remains enabled. Never retain/pass hidden reasoning.
                payload["thinking"] = {"type": "disabled"}
                for tool in payload["tools"]:
                    tool.get("function", {}).pop("strict", None)
            with httpx.Client(transport=self._transport, timeout=timeout, follow_redirects=False) as client:
                response = client.post(self.base_url + "/chat/completions", headers={
                    "Authorization": "Bearer " + self._key,
                }, json=payload)
            response.raise_for_status()
            payload = response.json()
            choice = payload["choices"][0]
            if choice.get("finish_reason") in {"length", "content_filter", "insufficient_system_resource", "aborted"}:
                raise ModelError("INCOMPLETE_MODEL_RESPONSE", "模型输出被截断、过滤或服务中断",
                                 request_id=response.headers.get("x-request-id"),
                                 latency_ms=round((time.perf_counter() - started) * 1000, 3))
            raw = choice["message"]
            if self.provider == "deepseek" and raw.get("reasoning_content"):
                raise ModelError("UNEXPECTED_REASONING_MODE", "服务返回了未请求的思考内容，已丢弃；请核对模型与非思考模式支持",
                                 request_id=response.headers.get("x-request-id"),
                                 latency_ms=round((time.perf_counter() - started) * 1000, 3))
            message = {"role": "assistant", "content": raw.get("content")}
            if raw.get("tool_calls"):
                message["tool_calls"] = [
                    {"id": c["id"], "type": "function", "function": {
                        "name": c["function"]["name"], "arguments": c["function"]["arguments"],
                    }} for c in raw["tool_calls"]
                ]
            return ModelReply(message, response.headers.get("x-request-id"), payload.get("usage"),
                              round((time.perf_counter() - started) * 1000, 3))
        except httpx.HTTPStatusError as exc:
            raise ModelError("HTTP_ERROR", f"模型服务返回 HTTP {exc.response.status_code}，未切换 Mock",
                             request_id=exc.response.headers.get("x-request-id"),
                             latency_ms=round((time.perf_counter() - started) * 1000, 3)) from None
        except httpx.TimeoutException:
            raise ModelError("MODEL_TIMEOUT", "模型请求超时，未自动重试",
                             latency_ms=round((time.perf_counter() - started) * 1000, 3)) from None
        except httpx.RequestError:
            raise ModelError("MODEL_TRANSPORT_ERROR", "无法连接模型服务",
                             latency_ms=round((time.perf_counter() - started) * 1000, 3)) from None
        except (KeyError, IndexError, TypeError, ValueError):
            raise ModelError("MODEL_PROTOCOL_ERROR", "模型响应不符合 Chat Completions 工具调用格式",
                             request_id=response.headers.get("x-request-id") if response is not None else None,
                             latency_ms=round((time.perf_counter() - started) * 1000, 3)) from None
