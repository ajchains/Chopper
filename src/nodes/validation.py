from __future__ import annotations

import logging

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from dag_utils import print_dag, to_markdown
from io_utils import awrite, awrite_json, log_and_record_error
from schemas import ValidationOutput, categories_for_prompt
from state import State

logger = logging.getLogger("pipeline")


def build_chain(prompts: dict, llm):
    parser = PydanticOutputParser(pydantic_object=ValidationOutput)
    return (
        ChatPromptTemplate.from_messages(
            [
                ("system", prompts["dag_validation"]),
                ("user", "# Original DAG: {dag}\n\n# Verification Reports:\n{changes}"),
            ]
        ).partial(categories=categories_for_prompt)
        | llm
        | parser
    )


async def _write(out: ValidationOutput, state: State) -> None:
    try:
        body = (
            "# DAG\n" + print_dag(out.final_dag) + "\n\n---\n\n"
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
                "dag": out.final_dag,
                "total_tasks": len(out.final_dag),
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
        }
    )

    await _write(out, state)

    return {
        "dag": out.final_dag,
        "total_tasks": len(out.final_dag),
        "validation_summary": out.validation_summary,
        "accepted_changes": out.accepted_changes,
        "rejected_changes": out.rejected_changes,
        "output_file_resolutions": out.output_file_resolutions,
        "phase": "dependency_resolution",
    }