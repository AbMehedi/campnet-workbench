import json
import logging
import sys

import pytest

from app.core.logging import FirstLineFilter, JsonFormatter, configure_logging, request_id_var


def _record(msg: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("campnet.test", logging.INFO, __file__, 1, msg, None, None)
    record.__dict__.update(extra)
    return record


def test_formatter_emits_single_line_json_with_base_fields() -> None:
    line = JsonFormatter("api").format(_record("hello\nworld"))
    assert "\n" not in line
    entry = json.loads(line)
    assert entry["level"] == "INFO"
    assert entry["service"] == "api"
    assert entry["logger"] == "campnet.test"
    assert entry["message"] == "hello\nworld"
    assert entry["request_id"] is None
    assert entry["timestamp"].endswith("+00:00")


def test_formatter_keeps_bangla_and_mixed_script_text() -> None:
    message = "বাংলা লেখা — ক্ষ্‌ ZWNJ‌ ZWJ‍ 👩‍👩‍👧"
    line = JsonFormatter("worker").format(_record(message))
    assert message in line  # not \u-escaped
    assert json.loads(line)["message"] == message


def test_formatter_emits_only_allowlisted_extra_fields() -> None:
    entry = json.loads(
        JsonFormatter("worker").format(
            _record("x", code="NOT_FOUND", status=404, arguments=["secret"], kwargs={"a": 1})
        )
    )
    assert entry["code"] == "NOT_FOUND"
    assert entry["status"] == 404
    assert "arguments" not in entry
    assert "kwargs" not in entry


def test_request_id_is_stamped_at_record_creation() -> None:
    configure_logging("api", "INFO", include_traceback=False)
    token = request_id_var.set("req-123")
    try:
        record = logging.getLogger("campnet.test").makeRecord(
            "campnet.test", logging.INFO, __file__, 1, "x", (), None
        )
    finally:
        request_id_var.reset(token)
    # Formatted after the context ended, still carries the ID.
    assert json.loads(JsonFormatter("api").format(record))["request_id"] == "req-123"


def test_configure_logging_is_idempotent_and_keeps_foreign_handlers() -> None:
    root = logging.getLogger()
    foreign = logging.NullHandler()
    root.addHandler(foreign)
    try:
        configure_logging("api", "INFO", include_traceback=False)
        configure_logging("api", "INFO", include_traceback=False)
        owned = [h for h in root.handlers if isinstance(h.formatter, JsonFormatter)]
        assert len(owned) == 1
        assert foreign in root.handlers
    finally:
        root.removeHandler(foreign)


def _record_with_exception() -> logging.LogRecord:
    try:
        raise ValueError("SELECT * FROM posts WHERE text = 'private'")
    except ValueError:
        record = _record("failed")
        record.exc_info = sys.exc_info()
    return record


def test_formatter_omits_traceback_unless_enabled() -> None:
    record = _record_with_exception()
    assert "private" not in JsonFormatter("api").format(record)
    entry = json.loads(JsonFormatter("api", include_traceback=True).format(record))
    assert "ValueError" in entry["traceback"]


def test_first_line_filter_drops_embedded_traceback() -> None:
    record = logging.LogRecord(
        "rq.worker", logging.ERROR, __file__, 1, "%s", ("Job failed\nTraceback: secret",), None
    )
    assert FirstLineFilter().filter(record)
    assert record.getMessage() == "Job failed"


def _owned_handler() -> logging.Handler:
    [handler] = [h for h in logging.getLogger().handlers if isinstance(h.formatter, JsonFormatter)]
    return handler


@pytest.mark.parametrize("name", ["rq.worker", "rq.job", "rq.queue"])
def test_worker_logging_truncates_all_rq_loggers_outside_development(name: str) -> None:
    from app.core.config import Settings
    from app.worker import configure_worker_logging

    configure_worker_logging(Settings(app_env="production"))
    record = logging.LogRecord(name, logging.ERROR, __file__, 1, "Job x failed\nsecret", (), None)
    assert _owned_handler().filter(record)
    assert record.getMessage() == "Job x failed"

    other = logging.LogRecord("app.x", logging.INFO, __file__, 1, "a\nb", (), None)
    assert _owned_handler().filter(other)
    assert other.getMessage() == "a\nb"


def test_worker_logging_keeps_full_rq_messages_in_development() -> None:
    from app.core.config import Settings
    from app.worker import configure_worker_logging

    configure_worker_logging(Settings(app_env="development"))
    record = logging.LogRecord("rq.job", logging.ERROR, __file__, 1, "a\nb", (), None)
    assert _owned_handler().filter(record)
    assert record.getMessage() == "a\nb"


def test_rq_does_not_install_its_own_handlers_once_configured() -> None:
    from rq.logutils import setup_loghandlers

    from app.core.config import Settings
    from app.worker import configure_worker_logging

    configure_worker_logging(Settings(app_env="production"))
    setup_loghandlers("INFO", name="rq.worker")
    rq_logger = logging.getLogger("rq.worker")
    assert rq_logger.handlers == []
    assert rq_logger.propagate is True
