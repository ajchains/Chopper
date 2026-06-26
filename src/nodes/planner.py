from __future__ import annotations

import json
import logging

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from dag_utils import print_dag
from io_utils import awrite, awrite_json, log_and_record_error
from prompts import partial_fill_prompts
from schemas import PlannerOutput, categories_for_prompt
from state import State

logger = logging.getLogger("pipeline")


def build_chain(prompts: dict, llm):
    parser = PydanticOutputParser(pydantic_object=PlannerOutput)
    return (
        ChatPromptTemplate.from_messages(
            [("system", prompts["planner"]), ("user", "{user_prompt}")]
        ).partial(categories=categories_for_prompt)
        | llm
        | parser
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


async def planner_agent(state: State, chain, prompts: dict) -> State:
    logger.info("PLANNER AGENT")
    out = await chain.ainvoke({"user_prompt": state["prompt"]})

    partial_fill_prompts(prompts, out.project_summary)
    await _write(out)

    await awrite_json(
        "snapshots/planner_output.json",
        {
            "project_summary": out.project_summary,
            "dag": out.dag,
            "total_tasks": len(out.dag),
            "phase": "dag_verification",
        },
    )

    return {
        "project_summary": out.project_summary,
        "decomposition_strategy": out.decomposition_strategy,
        "dag": out.dag,
        "total_tasks": len(out.dag),
        "phase": "dag_verification",
    }