from __future__ import annotations

import asyncio
import logging
from typing import Dict

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from dag_utils import print_dag, to_markdown
from fanout import run_fanout
from io_utils import awrite, awrite_json, log_and_record_error
from schemas import ExecutorOutput, Task
from state import DEFAULT_POOL, State

logger = logging.getLogger("pipeline")


def build_chain(prompts: dict, llm):
    parser = PydanticOutputParser(pydantic_object=ExecutorOutput)
    return (
        ChatPromptTemplate.from_messages(
            [
                ("system", prompts["executor"]),
                (
                    "user",
                    "# DAG:\n{dag}\n\n\n# Dependency Contracts:\n{dependency_contracts}"
                    "\n\n\n# Your Task\nId: {task_id}\nName: {task_name}",
                ),
            ]
        )
        | llm
        | parser
    )


async def _write(out: ExecutorOutput, task_name: str) -> None:
    try:
        body = (
            f"# Task {out.task_id} {task_name}\n\n---\n\n"
            "## Summary\n" + out.task_summary + "\n\n---\n\n"
            "## Output File\n" + str(out.output_file) + "\n\n---\n\n"
        )
        await awrite("outputs/executor_agent.md", body, mode="a")
    except Exception as e:
        await log_and_record_error("executor", e)


async def executor(state: State, chain) -> State:
    logger.info("EXECUTOR")
    dag: Dict[str, Task] = state["dag"]
    task_ids = list(dag.keys())
    #pool = min(len(task_ids), state.get("pool", DEFAULT_POOL))
    dependency_contracts_string = to_markdown(state["dependency_contracts"])

    inputs = [
        {
            "dag": print_dag(dag, own_task=tid),
            "dependency_contracts": dependency_contracts_string,
            "task_id": tid,
            "task_name": dag[tid].task_name,
            "project_summary": state["project_summary"],
        }
        for tid in task_ids
    ]

    #implementations, failures = await run_fanout(chain, inputs, pool, "executor")
    implementations, failures = await run_fanout(chain, inputs, "executor")

    await asyncio.gather(*(_write(out, dag[out.task_id].task_name) for out in implementations))

    await awrite_json("snapshots/executor_output.json", implementations)

    # implementations, not implementation — matches State's field name
    return {"implementations": implementations}