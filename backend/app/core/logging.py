"""Structured JSON logging (design §14.1).

One JSON object per line on stdout. Only allowlisted ``extra`` fields are emitted, so libraries
that attach arbitrary data to log records (e.g. RQ job arguments) can't leak it. Tracebacks are
emitted only when explicitly enabled (development; see ADR 0003).
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Literal

Service = Literal["api", "worker"]

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# The only `extra` keys that may appear in a log line.
ALLOWED_EXTRA_FIELDS = ("code", "exc_type", "method", "path", "status", "duration_ms")


class JsonFormatter(logging.Formatter):
    def __init__(self, service: Service, *, include_traceback: bool = False) -> None:
        super().__init__()
        self.service = service
        self.include_traceback = include_traceback

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        for key in ALLOWED_EXTRA_FIELDS:
            if key in record.__dict__:
                entry[key] = record.__dict__[key]
        if self.include_traceback and record.exc_info:
            entry["traceback"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


_base_factory = logging.getLogRecordFactory()


def _record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    # Stamp the request ID when the record is created, so it survives deferred formatting.
    # Consequence: never pass `extra={"request_id": ...}` — logging refuses to overwrite it.
    record = _base_factory(*args, **kwargs)
    record.request_id = request_id_var.get()
    return record


class FirstLineFilter(logging.Filter):
    """Keep only the first line of messages from loggers under ``prefix``.

    RQ embeds the formatted traceback (including the exception text, which may contain post
    content or SQL) in the message body itself, so dropping ``exc_info`` alone is not enough.
    Attached to the handler (not a logger) so it covers every child logger (rq.worker, rq.job...).
    """

    def __init__(self, prefix: str = "") -> None:
        super().__init__()
        self.prefix = prefix

    def filter(self, record: logging.LogRecord) -> bool:
        if self.prefix and not (
            record.name == self.prefix or record.name.startswith(self.prefix + ".")
        ):
            return True
        message = record.getMessage()
        if "\n" in message:
            record.msg = message.split("\n", 1)[0]
            record.args = None
        return True


class _OwnedHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Marker type so configure_logging only ever replaces its own handler."""


def configure_logging(
    service: Service,
    level: str,
    *,
    include_traceback: bool,
    first_line_only: tuple[str, ...] = (),
) -> None:
    """Install the JSON handler on the root logger. Safe to call more than once.

    ``first_line_only``: logger name prefixes whose messages are cut to their first line.
    """
    logging.setLogRecordFactory(_record_factory)
    root = logging.getLogger()
    for existing in [h for h in root.handlers if isinstance(h, _OwnedHandler)]:
        root.removeHandler(existing)
    handler = _OwnedHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service, include_traceback=include_traceback))
    for prefix in first_line_only:
        handler.addFilter(FirstLineFilter(prefix))
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn installs its own plain-text handlers with propagate=False; route through ours.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(logging.NOTSET)  # follow LOG_LEVEL
    # Uvicorn's access log includes query strings; our middleware writes the access line.
    logging.getLogger("uvicorn.access").disabled = True
