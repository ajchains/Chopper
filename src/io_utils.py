"""Async, non-blocking file I/O helpers used by every node's *_write function."""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any

import aiofiles

from schemas import serializer

logger = logging.getLogger("pipeline")


async def awrite(path: str, content: str, mode: str = "w") -> None:
    async with aiofiles.open(path, mode) as f:
        await f.write(content)


async def awrite_json(path: str, obj: Any) -> None:
    content = json.dumps(obj, indent=4, default=serializer)
    async with aiofiles.open(path, "w") as f:
        await f.write(content)


async def log_and_record_error(phase: str, exc: Exception) -> None:
    logger.error("Exception while writing output for %s: %s", phase, exc)
    async with aiofiles.open("error.log", "a") as f:
        await f.write(f"{phase.upper()}\n\n")
        await f.write("".join(traceback.format_exception(exc)))
        await f.write("\n\n---\n\n")


def init_output_files() -> None:
    """Explicit truncation of the human-readable phase logs — call once from run.py, never at import time."""
    for name in ("dag_verification.md", "dependency_resolution.md", "executor_agent.md", "evaluator_agent.md"):
        with open(f"outputs/{name}", "w") as f:
            f.write("")