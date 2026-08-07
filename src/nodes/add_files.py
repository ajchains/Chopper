from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import aiofiles

from state import State

logger = logging.getLogger("pipeline")


async def add_files(state: State) -> State:
    logger.info("ADD FILES")
    implementations = state["implementations"]
    output_files = {task_id : task.output_file for task_id, task in state["dag"].items()}

    async def write_one(impl):
        output_file = output_files[impl.task_id]
        logger.debug("writing %s", impl.task_id)
        path = Path("executor_output") / output_file.path
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, output_file.mode) as f:
            await f.write(impl.implementation)

    await asyncio.gather(*(write_one(impl) for impl in implementations))
    return {}