from __future__ import annotations

import json
import logging

from langchain_core.prompts import ChatPromptTemplate

from dag_utils import print_dag
from io_utils import awrite, awrite_json, log_and_record_error
from prompts import partial_fill_prompts
from schemas import PlannerOutput, compute_parallelism_analysis, ParallelismAnalysis
from state import State

logger = logging.getLogger("pipeline")


def build_chain(prompts: dict, llm):
    return (
        ChatPromptTemplate.from_messages(
            [("system", prompts["planner"]), ("user", "{{user_prompt}}")],
            template_format = "mustache"
        )
        | llm.with_structured_output(PlannerOutput)
    )


async def _write(out: PlannerOutput) -> None:
    try:
        body = (
            "# DAG\n" + print_dag(out.dag) + "\n\n---\n\n"
            "# Project Summary\n" + out.project_summary + "\n\n---\n\n"
            "# Decomposition Strategy\n" + out.decomposition_strategy
        )
        await awrite("outputs/planner_agent.md", body)
    except Exception as e:
        await log_and_record_error("planner", e)


async def planner_agent(state: State, chain) -> State:
    logger.info("PLANNER AGENT")
    out = await chain.ainvoke({"user_prompt": state["prompt"]})

    analysis_dict = compute_parallelism_analysis(out.dag)
    parallelism_analysis = ParallelismAnalysis(**analysis_dict)

    # partial_fill_prompts(prompts, out.project_summary)
    await _write(out)

    await awrite_json(
        "snapshots/planner_output.json",
        {
            "project_summary": out.project_summary,
            "dag": out.dag,
            "parallelism_analysis": parallelism_analysis,
            "total_tasks": len(out.dag),
            "phase": "dag_verification",
        },
    )

    return {
        "project_summary": out.project_summary,
        "decomposition_strategy": out.decomposition_strategy,
        "dag": out.dag,
        "parallelism_analysis": parallelism_analysis,
        "total_tasks": len(out.dag),
        "phase": "dag_verification",
    }