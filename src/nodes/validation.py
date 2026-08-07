from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate

from dag_utils import print_dag, to_markdown
from io_utils import awrite, awrite_json, log_and_record_error
from schemas import ValidationOutput, compute_parallelism_analysis
from state import State

logger = logging.getLogger("pipeline")


def build_chain(prompts: dict, llm):
    return (
        ChatPromptTemplate.from_messages(
            [
                ("system", prompts["dag_validation"]),
                (
                    "user",
                    "# Original DAG: {dag}\n\n"
                    "# Verification Reports:\n{changes}"
                    "# Project Summary\n{project_summary}\n\n"
                    "# Parallelism Analysis (Computed)\n{parallelism_analysis}\n\n"
                ),
            ]
        )
        | llm.with_structured_output(ValidationOutput)
    )


async def _write(out: ValidationOutput, state: State) -> None:
    try:
        body = (
            "# DAG\n" + print_dag(out.dag) + "\n\n---\n\n"
            "# Project Summary\n" + str(out.project_summary) + "\n\n---\n\n"
            "# Validation Summary\n" + str(out.validation_summary) + "\n\n---\n\n"
            "# Accepted Changes\n" + str(out.accepted_changes) + "\n\n---\n\n"
            "# Rejected Changes\n" + to_markdown(out.rejected_changes)
        )
        await awrite("outputs/dag_validation.md", body)

        await awrite_json(
            "snapshots/dag_validation.json",
            {
                **state,
                "dag": out.dag,
                "total_tasks": len(out.dag),
                "accepted_changes": out.accepted_changes,
                "rejected_changes": out.rejected_changes,
                "phase": "dependency_resolution",
            },
        )
    except Exception as e:
        await log_and_record_error("dag_validation", e)


async def dag_validation(state: State, chain) -> State:
    logger.info("DAG VALIDATION")

    if state["changes_required"] == 0:
        return {"phase": "dependency_resolution"}

    out = await chain.ainvoke(
        {
            "dag": print_dag(state["dag"]),
            "changes": to_markdown(state["changes"]),
            "project_summary": state["project_summary"],
            "parallelism_analysis": to_markdown(state["parallelism_analysis"]),
        }
    )
    parallelism_analysis = compute_parallelism_analysis(out.dag)

    await _write(out, state)

    return {
        "dag": out.dag,
        "total_tasks": len(out.dag),
        "validation_summary": out.validation_summary,
        "accepted_changes": out.accepted_changes,
        "rejected_changes": out.rejected_changes,
        "output_file_resolutions": out.output_file_resolutions,
        "parallelism_analysis": parallelism_analysis,
        "phase": "dependency_resolution",
    }