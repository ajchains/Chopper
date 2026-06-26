"""Prompt loading. No import-time disk I/O — load_prompts() is called explicitly from run.py."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

PROMPTS_DIR = "prompts"

NODE_FILENAMES = {
    "prompt":                "0. prompt_agent.md",
    "refine_prompt":         "0. prompt_agent.md",
    "planner":               "1. planner_agent.md",
    "dag_verification":      "2. dag_verification.md",
    "dag_validation":        "3. dag_validation.md",
    "dependency_resolution": "4. dependency_resolution.md",
    "coordinator":           "5. coordinator_agent.md",
    "executor":              "6. executor_agent.md",
    "evaluator":             "7. evaluator_agent.md",
}


def load_prompts(directory: str = PROMPTS_DIR) -> Dict[str, str]:
    loaded: Dict[str, str] = {}
    for phase, filename in NODE_FILENAMES.items():
        path = Path(directory) / filename
        try:
            loaded[phase] = path.read_text()
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Missing prompt file for phase '{phase}': {path}"
            ) from e
    return loaded


def partial_fill_prompts(prompts: Dict[str, str], project_summary: str) -> None:
    for phase, prompt in prompts.items():
        try:
            prompts[phase] = prompt.format(project_summary=project_summary)
        except Exception:
            pass