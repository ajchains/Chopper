"""Builds the per-phase LLM routers from config.yaml, via llm.get_llm()."""

from __future__ import annotations

from typing import Dict

from pool_manager.llm import MultiProviderChatLLM, get_llm


CONFIG_PATH = "configs/llm_config.yaml"
T_PLANNER = 1.0


def build_llms(config_path: str = CONFIG_PATH) -> Dict[str, MultiProviderChatLLM]:
    llm = get_llm(config_path, temperature=0.0)

    return {
        "refine_prompt": llm,
        "planner": llm,
        "dag_verification": llm,
        "dag_validation": llm,
        "dependency_resolution": llm,
        "coordinator": llm,
        "executor": llm,
        "evaluator": llm,
    }