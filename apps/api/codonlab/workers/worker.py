"""The worker process.

    python -m codonlab.workers.worker

Ours rather than the `rq worker` CLI so that the queue name, the connection and
the log line all come from the same configuration the API reads, instead of being
repeated in a compose command where they can drift apart.
"""

from __future__ import annotations

import logging
import sys

from rq import Worker

from codonlab.config import get_settings
from codonlab.queue import QUEUE_NAME, get_queue

logger = logging.getLogger("codonlab.worker")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_settings()
    logger.info(
        "starting worker: queue=%s redis=%s providers=%s",
        QUEUE_NAME,
        settings.redis_url,
        ",".join(settings.providers),
    )
    queue = get_queue()
    Worker([queue], connection=queue.connection).work(with_scheduler=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
