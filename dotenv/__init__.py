"""Minimal local fallback for `python-dotenv`.

This project only needs `dotenv_values()` because `chromadb` imports it
through Pydantic v1 when a `.env` file exists. Providing this lightweight
implementation keeps the app runnable even when `python-dotenv` is absent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def dotenv_values(dotenv_path: Optional[str] = None, encoding: str = "utf-8", **_: object) -> Dict[str, str]:
    path = Path(dotenv_path or ".env")
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding=encoding).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_quotes(value.strip())
        values[key] = value

    return values
