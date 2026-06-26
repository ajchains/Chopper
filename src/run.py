"""Entry point — run the full pipeline from the command line."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from graph import build_graph, prepare_app
from io_utils import init_output_files
from state import default_state

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")

async def has_checkpoint(app, config) -> bool:
    snapshot = await app.aget_state(config)
    return bool(snapshot.values)


async def main(
    question: str | None = None,
    config_path: str = "configs/llm_config.yaml",
    prompts_dir: str = "prompts",
    db_path: str = "checkpoints.db",
    thread_id: str | None = None,
    pool: int = 8,
) -> dict:

    Path("outputs").mkdir(exist_ok=True)
    Path("snapshots").mkdir(exist_ok=True)
    Path("executor_output").mkdir(exist_ok=True)
    init_output_files()

    prompts, llms = prepare_app(config_path=config_path, prompts_dir=prompts_dir)

    
    #state["pool"] = pool

    config = {"configurable": {"thread_id": thread_id or str(uuid.uuid4())}}

    async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
        app = build_graph(prompts, llms, checkpointer)
        logger.info("Starting pipeline  thread=%s", config["configurable"]["thread_id"])

        if await has_checkpoint(app, config):
            result = await app.ainvoke(None, config=config)
        else:
            if question is None:
                question = input("Enter your task: ").strip()

            state = default_state()
            state["question"] = question
            result = await app.ainvoke(state, config=config)

    logger.info("Pipeline complete")
    logger.info(
        "Passed: %d | Failed: %d | Avg score: %.2f",
        result.get("passed_tasks", 0),
        result.get("failed_tasks", 0),
        result.get("average_score", 0.0),
    )

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the multi-agent coding pipeline.")
    parser.add_argument("question", nargs="?", help="Task description (prompted if omitted)")
    parser.add_argument("--config",  default="configs/llm_config.yaml", help="Path to LLM config YAML")
    parser.add_argument("--prompts", default="prompts",                  help="Directory containing prompt .md files")
    parser.add_argument("--db",      default="checkpoints.db",           help="SQLite checkpoint DB path")
    parser.add_argument("--thread",  default=None,                       help="Thread ID for checkpointing (auto if omitted)")
    parser.add_argument("--pool",    type=int, default=8,                help="Max concurrent fan-out tasks")
    args = parser.parse_args()

    asyncio.run(
        main(
            question=args.question,
            config_path=args.config,
            prompts_dir=args.prompts,
            db_path=args.db,
            thread_id=args.thread,
            pool=args.pool,
        )
    )