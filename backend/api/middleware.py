import logging
import re
import time
import uuid

from backend.request_context import request_id_var

log = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestContextMiddleware:
    """Gives every request an ID, logs it, and echoes the ID back in the response.

    An `X-Request-ID` sent by the caller is reused (if it looks sane) so a call can be
    followed across services; otherwise one is generated. Listed first in MIDDLEWARE so
    every other log line, including errors raised by other middleware, carries the ID.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = supplied if _VALID_REQUEST_ID.match(supplied) else uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            log.info("request received method=%s path=%s", request.method, request.path)
            response = self.get_response(request)
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.info(
                "request completed method=%s path=%s status=%d duration_ms=%.1f",
                request.method, request.path, response.status_code, elapsed_ms,
            )
            response[REQUEST_ID_HEADER] = request_id
            if request.path.startswith("/api/"):
                response["Cache-Control"] = "no-store"
            return response
        finally:
            request_id_var.reset(token)
