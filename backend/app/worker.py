"""Background worker entry point (RQ). Run with: python -m app.worker

Long-running jobs (imports, media downloads, OCR, exports) are enqueued by the API and
executed here. Job modules live under app/processing/ as they are implemented.
"""

from redis import Redis
from rq import Queue, Worker

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging

QUEUE_NAMES = ["default"]


def configure_worker_logging(settings: Settings) -> None:
    include_traceback = settings.app_env == "development"  # ADR 0003
    configure_logging(
        "worker",
        settings.log_level,
        include_traceback=include_traceback,
        # RQ puts formatted tracebacks (with exception text) into messages on rq.* loggers.
        first_line_only=() if include_traceback else ("rq",),
    )


def main() -> None:
    settings = get_settings()
    configure_worker_logging(settings)
    connection = Redis.from_url(settings.redis_url)
    queues = [Queue(name, connection=connection) for name in QUEUE_NAMES]
    # log_job_description=False: job descriptions include the repr of job arguments.
    worker = Worker(queues, connection=connection, log_job_description=False)
    worker.work(logging_level=settings.log_level)


if __name__ == "__main__":
    main()
