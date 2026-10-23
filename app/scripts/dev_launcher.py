
from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("memorynest.dev_launcher")


def build_commands() -> list[tuple[str, list[str]]]:
    """Build the commands for all MemoryNest development processes."""
    return [
        (
            "Knowledge Graph worker",
            [
                sys.executable,
                "-m",
                "app.scripts.knowledge_graph_worker",
                "--poll-interval",
                "10",
                "--batch-size",
                "10",
            ],
        ),
        (
            "Notification delivery worker",
            [
                sys.executable,
                "-m",
                "app.scripts.notification_delivery_worker",
                "--watch",
                "--interval-seconds",
                "30",
                "--batch-size",
                "25",
            ],
        ),
        (
            "Streamlit",
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "app/main.py",
            ],
        ),
    ]


def main() -> int:
    processes: list[tuple[str, subprocess.Popen]] = []

    try:
        for name, command in build_commands():
            logger.info("Starting %s...", name)
            process = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
            )
            processes.append((name, process))
            time.sleep(1)

            if process.poll() is not None:
                logger.error(
                    "%s exited during startup with code %s.",
                    name,
                    process.returncode,
                )
                return int(process.returncode or 1)

        logger.info(
            "MemoryNest is running at http://localhost:8501. "
            "Knowledge Graph and notification workers are active. "
            "Press Ctrl+C to stop all processes."
        )

        while True:
            for name, process in processes:
                return_code = process.poll()
                if return_code is not None:
                    logger.error(
                        "%s exited with code %s.",
                        name,
                        return_code,
                    )
                    return int(return_code or 1)

            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Shutdown requested.")

    finally:
        for name, process in reversed(processes):
            if process.poll() is None:
                logger.info("Stopping %s...", name)
                process.terminate()

        for name, process in reversed(processes):
            if process.poll() is None:
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    logger.warning("Force-stopping %s.", name)
                    process.kill()
                    process.wait()

        logger.info("Launcher stopped.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
