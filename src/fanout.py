"""Shared fan-out helper — replaces every ThreadPoolExecutor block with .abatch()."""

from __future__ import annotations

import logging

logger = logging.getLogger("pipeline")

#async def run_fanout(chain, inputs: list[dict], max_concurrency: int, label:str):
async def run_fanout(chain, inputs: list[dict], label: str):
    """
    Runs `chain.abatch(inputs)` with per-task failure isolation
    """
    # results = await chain.abatch(
    #     inputs, config={"max_concurrency": max_concurrency}, return_exceptions=True
    # )
    # results = await chain.abatch(
    #     inputs, return_exceptions=True
    # )
    # successes, failures = [], []
    # for inp, res in zip(inputs, results):
    #     if isinstance(res, Exception):
    #         failures.append((inp, res))
    #         logger.error("%s task failed (task_id=%s): %s", label, inp.get("task_id"), res)
    #     else:
    #         successes.append(res)
    # return successes, failures

    retries_left = 2
    remaining = inputs
    successes = []
    failures = []

    while retries_left:
        if not remaining:
            break
        
        results = await chain.abatch(
            remaining, return_exceptions=True
        )

        next_remaining = []

        for inp, res in zip(remaining,results):
            if isinstance(res, Exception):
                logger.error("%s task failed (task_id=%s): %s", label, inp.get("task_id"), res)
                next_remaining.append(inp)
            else:
                successes.append(res)
        
        retries_left-=1
        remaining = next_remaining

    failures = remaining

    return successes, failures
                