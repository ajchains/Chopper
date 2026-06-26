from __future__ import annotations

import asyncio
import logging
from typing import Dict

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from dag_utils import print_dag
from fanout import run_fanout
from io_utils import awrite, awrite_json, log_and_record_error
from schemas import DependencySpecOutput, Task
from state import DEFAULT_POOL, State

logger = logging.getLogger("pipeline")


def build_chain(prompts: dict, llm):
    parser = PydanticOutputParser(pydantic_object=DependencySpecOutput)
    return (
        ChatPromptTemplate.from_messages(
            [
                ("system", prompts["dependency_resolution"]),
                ("user", "# DAG: {dag}\n\n# Your Task\nId: {task_id}\nName: {task_name}"),
            ]
        )
        | llm
        | parser
    )


async def _write(out: DependencySpecOutput, task_name: str) -> None:
    try:
        parts = [f"# Dependency Resolution\n\n---\n\n## Task {out.task_id} {task_name}\n\n---\n\n"]
        for spec in out.dependency_specifications:
            parts.append(
                "## Depends On Task\n" + str(spec.depends_on_task_id) + "\n\n"
                "### Dependency Name\n" + str(spec.dependency_name) + "\n\n"
                "### Purpose\n" + str(spec.purpose) + "\n\n"
                "### Example\n" + str(spec.example) + "\n\n---\n\n"
            )
        await awrite("outputs/dependency_resolution.md", "".join(parts), mode="a")
    except Exception as e:
        await log_and_record_error("dependency_resolution", e)


async def dependency_resolution(state: State, chain) -> State:
    logger.info("DEPENDENCY RESOLUTION")
    dag: Dict[str, Task] = state["dag"]
    task_ids = list(dag.keys())
    #pool = min(len(task_ids), state.get("pool", DEFAULT_POOL))

    inputs = [
        {
            "dag": print_dag(dag, own_task=tid),
            "task_id": tid,
            "task_name": dag[tid].task_name,
            "project_summary": state["project_summary"],
        }
        for tid in task_ids
    ]

    #issues, failures = await run_fanout(chain, inputs, pool, "dependency_resolution")
    issues, failures = await run_fanout(chain, inputs ,"dependency_resolution")

    await asyncio.gather(*(_write(out, dag[out.task_id].task_name) for out in issues))

    await awrite_json("snapshots/dependency_resolution_issues.json", issues)

    return {"dependency_specs": issues}