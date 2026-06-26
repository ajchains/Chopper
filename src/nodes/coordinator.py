from __future__ import annotations

import logging

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from dag_utils import print_dag, to_markdown
from io_utils import awrite, awrite_json, log_and_record_error
from schemas import CoordinatorOutput
from state import State

logger = logging.getLogger("pipeline")


def build_chain(prompts: dict, llm):
    parser = PydanticOutputParser(pydantic_object=CoordinatorOutput)
    return (
        ChatPromptTemplate.from_messages(
            [
                ("system", prompts["coordinator"]),
                ("user", "# Final DAG: {dag}\n\n# Dependency Specifications:\n{specifications}"),
            ]
        )
        | llm
        | parser
    )


async def _write(out: CoordinatorOutput, state: State) -> None:
    try:
        body = (
            "# Integration Summary\n" + out.integration_summary + "\n\n---\n\n"
            "# Resolved Conflicts\n" + to_markdown(out.resolved_conflicts) + "\n\n---\n\n"
            "# Dependency Contracts\n" + to_markdown(out.dependency_contracts)
        )
        await awrite("outputs/coordinator_agent.md", body)

        await awrite_json(
            "snapshots/coordinator_output.json",
            {
                **state,
                "resolved_conflicts": out.resolved_conflicts,
                "dependency_contracts": out.dependency_contracts,
                "dag": out.dag,
                "phase": "executor",
            },
        )
    except Exception as e:
        await log_and_record_error("coordinator", e)


async def coordinator(state: State, chain) -> State:
    logger.info("COORDINATOR")
    out = await chain.ainvoke(
        {
            "dag": print_dag(state["dag"]),
            "specifications": to_markdown(state["dependency_specs"]),
            "project_summary": state["project_summary"],
        }
    )

    await _write(out, state)

    return {
        "dag": out.dag,
        "integration_summary": out.integration_summary,
        "resolved_conflicts": out.resolved_conflicts,
        "dependency_contracts": out.dependency_contracts,
        "phase": "executor",
    }