"""Worker process runner for background jobs and branch reconciliation."""

from __future__ import annotations

import asyncio
import logging
import signal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("unpack.worker")


async def run_worker():
    logger.info("Unpack background worker starting up...")
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Signal handlers not implemented on Windows event loop
            pass

    while not stop_event.is_set():
        # Heartbeat & Job Poll Tick
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            break

    logger.info("Unpack background worker shutting down cleanly.")


def main():
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
