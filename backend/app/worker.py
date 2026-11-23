"""Background worker entry point (RQ). Run with: python -m app.worker

Long-running jobs (imports, media downloads, OCR, exports) are enqueued by the API and
executed here. Job modules live under app/processing/ as they are implemented.
"""

import logging

from redis import Redis
from rq import Queue, Worker

from app.core.config import get_settings

QUEUE_NAMES = ["default"]


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    connection = Redis.from_url(settings.redis_url)
    queues = [Queue(name, connection=connection) for name in QUEUE_NAMES]
    Worker(queues, connection=connection).work()


if __name__ == "__main__":
    main()
