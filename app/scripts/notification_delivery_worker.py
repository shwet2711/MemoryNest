
from __future__ import annotations

import argparse
import logging
import time

from app.db.session import SessionLocal
from app.services.notification_delivery_worker import (
    process_due_notifications,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process due MemoryNest email reminders."
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep checking for due reminders.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=30,
        help="Polling interval in watch mode (default: 30).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Maximum reminders per run (default: 25).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.interval_seconds < 1:
        raise SystemExit("--interval-seconds must be at least 1.")

    if args.batch_size < 1:
        raise SystemExit("--batch-size must be at least 1.")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    logger = logging.getLogger("memorynest.notification_worker")
    logger.info(
        "Notification worker starting (watch=%s, interval=%s, batch_size=%s).",
        args.watch,
        args.interval_seconds,
        args.batch_size,
    )

    try:
        while True:
            with SessionLocal() as db:
                stats = process_due_notifications(
                    db,
                    batch_size=args.batch_size,
                )

            logger.info("Notification worker results: %s", stats)

            if not args.watch:
                break

            time.sleep(args.interval_seconds)

    except KeyboardInterrupt:
        logger.info("Notification worker stopped.")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
