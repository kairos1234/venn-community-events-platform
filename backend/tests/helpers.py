import json
import logging
from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import TestCase

from backend.request_context import current_request_id

VISITOR = {}
ADMIN = {"X-Demo-Role": "admin"}
ORGANISER_1 = {"X-Demo-Role": "organiser", "X-Demo-Organiser-Id": "organiser-1"}
ORGANISER_2 = {"X-Demo-Role": "organiser", "X-Demo-Organiser-Id": "organiser-2"}


def future_date(days: int = 7) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def event_payload(**overrides) -> dict:
    payload = {
        "title": "Park Picnic",
        "description": "Bring a blanket.",
        "category": "Community",
        "starts_at": future_date(),
        "capacity": 10,
    }
    payload.update(overrides)
    return payload


class LogCapture(logging.Handler):
    """Records each log message together with the request ID that was current when it was logged."""

    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append((current_request_id(), record.levelname, record.getMessage()))

    def messages(self, request_id=None):
        return [m for rid, _, m in self.lines if request_id is None or rid == request_id]


class ApiTestCase(TestCase):
    """Small helpers around Django's test client for the JSON API."""

    def setUp(self):
        # Keep test output readable; tests that assert on logs switch logging back on.
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def capture_logs(self) -> LogCapture:
        """Send application logs to a capture handler only (not the console) for this test."""
        capture = LogCapture()
        patcher = mock.patch.object(logging.getLogger("backend"), "handlers", [capture])
        patcher.start()
        self.addCleanup(patcher.stop)
        logging.disable(logging.NOTSET)  # setUp switched logging off for readability
        return capture

    def get(self, path, headers=None):
        return self.client.get(path, headers=headers or {})

    def post(self, path, body=None, headers=None):
        if body is None:
            return self.client.post(path, headers=headers or {})
        return self.client.post(path, data=json.dumps(body), content_type="application/json", headers=headers or {})

    def put(self, path, body, headers=None):
        return self.client.put(path, data=json.dumps(body), content_type="application/json", headers=headers or {})

    def create_event(self, headers=ORGANISER_1, **overrides) -> dict:
        response = self.post("/api/events", event_payload(**overrides), headers)
        self.assertEqual(response.status_code, 201, response.json())
        return response.json()

    def create_published_event(self, **overrides) -> dict:
        event = self.create_event(**overrides)
        response = self.post(f"/api/events/{event['id']}/publish", headers=ADMIN)
        self.assertEqual(response.status_code, 200, response.json())
        return response.json()
