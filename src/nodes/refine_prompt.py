from __future__ import annotations

import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from io_utils import awrite
from prompts import NODE_FILENAMES
from state import State

logger = logging.getLogger("pipeline")


def build_chain(prompts: dict, llm):
    return (
        ChatPromptTemplate.from_messages(
            [("system", prompts["prompt"]), ("user", "{user_query}")]
        )
        | llm
        | StrOutputParser()
    )


async def refine_prompt(state: State, chain) -> State:
    logger.info("REFINE PROMPT")
    out = await chain.ainvoke({"user_query": state["question"]})
    await awrite(f"snapshots/{NODE_FILENAMES['prompt']}", out)
    return {"prompt": out, "phase": "planner"}