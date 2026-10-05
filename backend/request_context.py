"""Request-ID plumbing shared by the middleware, the log formatter and the activity records."""

import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def current_request_id() -> str:
    return request_id_var.get()


class RequestIdFormatter(logging.Formatter):
    """Adds the current request ID to every line and keeps user text from forging extra lines."""

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = current_request_id()
        return super().format(record)

    def formatMessage(self, record: logging.LogRecord) -> str:
        record.message = record.message.replace("\r", "\\r").replace("\n", "\\n")
        return super().formatMessage(record)
