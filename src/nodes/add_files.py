from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import aiofiles

from state import State

logger = logging.getLogger("pipeline")


async def add_files(state: State) -> State:
    logger.info("ADD FILES")

    async def write_one(impl):
        logger.debug("writing %s", impl.task_id)
        path = Path("executor_output") / impl.output_file.path
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, impl.output_file.mode) as f:
            await f.write(impl.implementation)

    await asyncio.gather(*(write_one(impl) for impl in state["implementations"]))
    return {}