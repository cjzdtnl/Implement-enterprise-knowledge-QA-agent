"""Explicit local configuration loading. Never evaluate or log secret values."""
from __future__ import annotations

import os
from pathlib import Path
import re


ENV_KEYS = frozenset({
    "LLM_API_KEY", "DEEPSEEK_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_PROVIDER",
    "MAX_STEPS", "MAX_TOOL_CALLS", "LLM_TIMEOUT_SECONDS", "RUN_TIMEOUT_SECONDS",
})


def load_env_file(path: Path) -> list[str]:
    """Subset of dotenv syntax: KEY=value, optional outer quotes/export, # comment lines.

    Process variables take precedence. No interpolation, inline comment stripping,
    shell execution, or automatic file discovery. Reject malformed files atomically.
    """
    pending = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or key not in ENV_KEYS or not re.fullmatch(r"[A-Z_]+", key):
            raise ValueError(f"配置文件第 {line_number} 行格式或变量名不受支持（不显示内容）")
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"配置文件第 {line_number} 行引号未闭合（不显示内容）")
            value = value[1:-1]
        if not value or "\x00" in value or key in pending:
            raise ValueError(f"配置文件第 {line_number} 行为空值、重复变量或非法字符（不显示内容）")
        pending[key] = value
    for key, value in pending.items():
        os.environ.setdefault(key, value)
    return sorted(pending)
