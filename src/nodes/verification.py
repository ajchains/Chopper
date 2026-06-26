from __future__ import annotations

import asyncio
import logging
from typing import Dict

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from dag_utils import print_dag
from fanout import run_fanout
from io_utils import awrite, awrite_json, log_and_record_error
from schemas import Task, VerificationOutput
from state import DEFAULT_POOL, State

logger = logging.getLogger("pipeline")


def build_chain(prompts: dict, llm):
    parser = PydanticOutputParser(pydantic_object=VerificationOutput)
    return (
        ChatPromptTemplate.from_messages(
            [
                ("system", prompts["dag_verification"]),
                ("user", "# DAG: {dag}\n\n# Your Task\nId: {task_id}\nName: {task_name}"),
            ]
        )
        | llm
        | parser
    )


async def _write(out: VerificationOutput, task_name: str) -> None:
    try:
        body = (
            "# DAG Verification\n\n---\n\n"
            f"## Task {out.task_id} {task_name}\n\n---\n\n"
            "### Dag Valid For Task\n" + str(out.dag_valid_for_task) + "\n\n---\n\n"
            "### Summary\n" + str(out.summary) + "\n\n---\n\n"
            "### Issues\n" + str(out.issues) + "\n\n---\n\n"
            "### Scope Corrections\n" + str(out.scope_corrections) + "\n\n---\n\n"
            "### Suggested Dag Changes\n" + str(out.suggested_dag_changes)
        )
        await awrite("outputs/dag_verification.md", body, mode="a")
    except Exception as e:
        await log_and_record_error("dag_verification", e)


async def dag_verification(state: State, chain) -> State:
    logger.info("DAG VERIFICATION")
    dag: Dict[str, Task] = state["dag"]
    task_ids = list(dag.keys())
    #pool = min(len(task_ids), state.get("pool", DEFAULT_POOL))

    inputs = [
        {"dag": print_dag(dag, own_task=tid), "task_id": tid, "task_name": dag[tid].task_name}
        for tid in task_ids
    ]

    #changes, failures = await run_fanout(chain, inputs, pool, "dag_verification")
    changes, failures = await run_fanout(chain, inputs, "dag_verification")

    await asyncio.gather(*(_write(out, dag[out.task_id].task_name) for out in changes))

    changes_required = sum(not c.dag_valid_for_task for c in changes)
    await awrite_json("snapshots/dag_verification_changes.json", changes)

    return {"changes": changes, "changes_required": changes_required}