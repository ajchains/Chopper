from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from dag_utils import to_markdown
from fanout import run_fanout
from io_utils import awrite, awrite_json, log_and_record_error
from schemas import DependencyContract, EvaluatorOutput, ExecutorOutput, Task
from state import State

logger = logging.getLogger("pipeline")


def build_chain(prompts: dict, llm):
    parser = PydanticOutputParser(pydantic_object=EvaluatorOutput)
    return (
        ChatPromptTemplate.from_messages(
            [
                SystemMessage(content=prompts["evaluator"]),
                (
                    "user",
                    "# Task Spec\n{task_spec}"
                    "\n\n\n# Dependency Contracts\n{dependency_contracts}"
                    "\n\n\n# Executor Output\nTask Id: {task_id}\n{executor_output}"
                    "\n\n\n# Peer Task Implementations\n{peer_implementations}",
                ),
            ]
        )
        | llm
        | parser
    )


async def _write(out: EvaluatorOutput, task_name: str) -> None:
    try:
        body = ""
        await awrite("outputs/evaluator_agent.md", body, mode="a")
    except Exception as e:
        await log_and_record_error("evaluator", e)


async def evaluator(state: State, chain) -> State:
    logger.info("EVALUATOR")

    return state