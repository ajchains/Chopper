"""Builds the compiled LangGraph app."""

from __future__ import annotations

from typing import Dict

from langgraph.graph import END, START, StateGraph

import nodes as node_registry
from llm_registry import build_llms
from nodes.add_files import add_files
from nodes.planner import planner_agent as planner_agent
from prompts import load_prompts
from state import State


def _make_node(fn, chain):
    async def _node(s):
        return await fn(s, chain)
    return _node


def _make_planner_node(fn, chain, prompts):
    async def _node(s):
        return await fn(s, chain, prompts)
    return _node


def build_graph(prompts: Dict[str, str], llms: Dict[str, object], checkpointer) -> object:
    graph = StateGraph(State)

    for phase, (build_chain, node_fn) in node_registry.REGISTRY.items():
        llm = llms[phase]
        chain = build_chain(prompts, llm)

        if node_fn is planner_agent:
            graph.add_node(phase, _make_planner_node(node_fn, chain, prompts))
        else:
            graph.add_node(phase, _make_node(node_fn, chain))

    graph.add_node("add_files", add_files)

    graph.add_edge(START, "refine_prompt")
    graph.add_edge("refine_prompt", "planner")
    graph.add_edge("planner", "dag_verification")
    graph.add_edge("dag_verification", "dag_validation")
    graph.add_edge("dag_validation", "dependency_resolution")
    graph.add_edge("dependency_resolution", "coordinator")
    graph.add_edge("coordinator", "executor")
    graph.add_edge("executor", "evaluator")
    graph.add_edge("evaluator", "add_files")
    graph.add_edge("add_files", END)

    return graph.compile(checkpointer=checkpointer)


def prepare_app(
    config_path: str = "configs/llm_config.yaml",
    prompts_dir: str = "prompts",
):
    prompts = load_prompts(prompts_dir)
    llms = build_llms(config_path)
    return prompts, llms