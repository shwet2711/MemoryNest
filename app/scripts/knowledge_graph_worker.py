from __future__ import annotations

import argparse
import logging
import time

from app.core.config import NEO4J_ENABLED
from app.db.init_db import init_database
from app.services.knowledge_graph_sync_worker import process_due_jobs


logger = logging.getLogger("memorynest.knowledge_graph_worker")


def positive_int(value: str) -> int:
    """Parse a positive integer for CLI arguments."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Value must be a positive integer."
        ) from exc

    if parsed < 1:
        raise argparse.ArgumentTypeError(
            "Value must be a positive integer."
        )

    return parsed


def positive_float(value: str) -> float:
    """Parse a positive polling interval."""
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Value must be a positive number."
        ) from exc

    if not 0 < parsed < float("inf"):
        raise argparse.ArgumentTypeError(
            "Value must be a finite positive number."
        )

    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Process queued MemoryNest Knowledge Graph synchronization "
            "and deletion jobs."
        )
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one batch and exit.",
    )
    parser.add_argument(
        "--poll-interval",
        type=positive_float,
        default=10.0,
        help="Seconds between batches in continuous mode (default: 10).",
    )
    parser.add_argument(
        "--batch-size",
        type=positive_int,
        default=10,
        help="Maximum jobs per batch (default: 10).",
    )
    return parser


def run_worker(
    *,
    once: bool = False,
    poll_interval: float = 10.0,
    batch_size: int = 10,
) -> int:
    """Initialize the database and run the worker."""
    if not NEO4J_ENABLED:
        logger.error(
            "Knowledge Graph worker cannot run because NEO4J_ENABLED "
            "is false. Enable Neo4j in your environment first."
        )
        return 2

    init_database()

    if once:
        processed = process_due_jobs(limit=batch_size)
        logger.info("Batch finished; %s job(s) processed.", processed)
        return 0

    logger.info(
        "Knowledge Graph worker started (batch_size=%s, poll_interval=%s). "
        "Press Ctrl+C to stop.",
        batch_size,
        poll_interval,
    )

    try:
        while True:
            try:
                processed = process_due_jobs(limit=batch_size)
                if processed:
                    logger.info(
                        "Batch finished; %s job(s) processed.",
                        processed,
                    )
            except Exception:
                # Keep the worker alive if a batch-level error occurs.
                logger.exception(
                    "Knowledge Graph batch failed; will retry after polling."
                )

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        logger.info("Shutdown requested; stopping Knowledge Graph worker.")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    return run_worker(
        once=args.once,
        poll_interval=args.poll_interval,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    raise SystemExit(main())
