from datetime import datetime, timedelta, timezone
from unittest import mock

from django.db import OperationalError, connection

from backend.events.models import Event
from backend.registrations.models import Registration
from backend.tests.helpers import ADMIN, ORGANISER_1, ApiTestCase, event_payload


class RegistrationRuleTests(ApiTestCase):
    def test_registration_succeeds_for_published_event_with_capacity(self):
        event = self.create_published_event(capacity=3)

        response = self.post(f"/api/events/{event['id']}/registrations")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["id"].startswith("REG-"))
        self.assertEqual(body["event_id"], event["id"])
        updated = self.get(f"/api/events/{event['id']}").json()
        self.assertEqual(updated["registration_count"], 1)
        self.assertEqual(updated["spots_remaining"], 2)

    def test_registration_is_rejected_for_unpublished_event(self):
        event = self.create_event()

        response = self.post(f"/api/events/{event['id']}/registrations")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "EVENT_NOT_PUBLISHED")
        self.assertEqual(Registration.objects.count(), 0)

    def test_registration_is_rejected_once_event_is_full(self):
        event = self.create_published_event(capacity=2)

        statuses = [self.post(f"/api/events/{event['id']}/registrations").status_code for _ in range(3)]

        self.assertEqual(statuses, [201, 201, 409])
        rejected = self.post(f"/api/events/{event['id']}/registrations")
        self.assertEqual(
            rejected.json(),
            {"code": "EVENT_FULL", "message": "Registration is no longer available because this event is full."},
        )
        self.assertEqual(self.get(f"/api/events/{event['id']}").json()["registration_count"], 2)

    def test_registration_is_rejected_once_the_event_has_started(self):
        event = self.create_published_event()
        Event.objects.filter(pk=event["id"]).update(starts_at=datetime(2000, 1, 1, 10, 0, tzinfo=timezone.utc))

        response = self.post(f"/api/events/{event['id']}/registrations")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"code": "REGISTRATION_CLOSED", "message": "Registration is closed because this event has already started."},
        )
        self.assertEqual(Registration.objects.count(), 0)
        self.assertEqual(self.get("/api/admin/activity", ADMIN).json()["activity"][0]["type"], "EVENT_PUBLISHED")

    def test_registration_closes_at_the_start_time_and_not_before(self):
        event = self.create_published_event()
        now = datetime.now(timezone.utc)

        Event.objects.filter(pk=event["id"]).update(starts_at=now + timedelta(hours=1))
        before_start = self.post(f"/api/events/{event['id']}/registrations")
        Event.objects.filter(pk=event["id"]).update(starts_at=now - timedelta(seconds=1))
        after_start = self.post(f"/api/events/{event['id']}/registrations")

        self.assertEqual(before_start.status_code, 201)
        self.assertEqual(after_start.status_code, 409)
        self.assertEqual(after_start.json()["code"], "REGISTRATION_CLOSED")

    def test_registration_for_unknown_event_is_404(self):
        response = self.post("/api/events/EVT-NOPE/registrations")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "EVENT_NOT_FOUND")

    def test_registration_stores_no_personal_data(self):
        event = self.create_published_event()
        # Extra request data must be ignored, not stored.
        self.client.post(
            f"/api/events/{event['id']}/registrations",
            data='{"name": "Jane Doe", "email": "jane@example.com"}',
            content_type="application/json",
            headers={"X-Forwarded-For": "203.0.113.9", "User-Agent": "test-agent"},
        )

        with connection.cursor() as cursor:
            cursor.execute(f"PRAGMA table_info({Registration._meta.db_table})")
            columns = [row[1] for row in cursor.fetchall()]
            cursor.execute(f"SELECT * FROM {Registration._meta.db_table}")
            stored = cursor.fetchall()

        self.assertCountEqual(columns, ["id", "event_id", "registered_at"])  # nothing else is stored
        self.assertEqual(len(stored), 1)
        self.assertNotIn("jane", str(stored).lower())
        self.assertNotIn("203.0.113.9", str(stored))


class ActivityTests(ApiTestCase):
    def test_registration_records_an_activity_entry(self):
        event = self.create_published_event()

        registration = self.post(f"/api/events/{event['id']}/registrations").json()

        activity = self.get("/api/admin/activity", ADMIN).json()["activity"]
        self.assertEqual(activity[0]["type"], "REGISTRATION_CREATED")
        self.assertIn(registration["id"], activity[0]["message"])

    def test_failed_registration_records_no_activity(self):
        event = self.create_event()

        self.post(f"/api/events/{event['id']}/registrations")

        self.assertEqual(self.get("/api/admin/activity", ADMIN).json()["activity"], [])


class LoggingAndErrorTests(ApiTestCase):
    def test_request_id_is_echoed_logged_and_stored_with_the_activity_entry(self):
        event = self.create_published_event()
        capture = self.capture_logs()

        response = self.client.post(f"/api/events/{event['id']}/registrations", headers={"X-Request-ID": "trace-123"})

        self.assertEqual(response["X-Request-ID"], "trace-123")
        messages = capture.messages("trace-123")
        steps = ["request received", "event validated", "registration stored", "activity recorded", "request completed"]
        positions = [next(i for i, m in enumerate(messages) if m.startswith(step)) for step in steps]
        self.assertEqual(positions, sorted(positions))
        activity = self.get("/api/admin/activity", ADMIN).json()["activity"]
        self.assertEqual(activity[0]["request_id"], "trace-123")

    def test_every_rejected_request_is_logged_with_its_error_code_but_not_the_submitted_values(self):
        capture = self.capture_logs()

        self.post("/api/events", event_payload(title="", capacity=0, description="private note"),
                  {**ORGANISER_1, "X-Request-ID": "rej-validation"})
        self.post("/api/events/EVT-1/publish", headers={"X-Request-ID": "rej-forbidden"})
        self.post("/api/events/EVT-NOPE/publish", headers={**ADMIN, "X-Request-ID": "rej-missing"})

        validation = capture.messages("rej-validation")
        self.assertTrue(any("status=400 code=VALIDATION_ERROR fields=title,capacity" in m for m in validation), validation)
        self.assertTrue(any("status=403 code=FORBIDDEN" in m for m in capture.messages("rej-forbidden")))
        self.assertTrue(any("status=404 code=EVENT_NOT_FOUND" in m for m in capture.messages("rej-missing")))
        self.assertNotIn("private note", " ".join(capture.messages()))
        self.assertIn("WARNING", [level for _, level, m in capture.lines if "request rejected" in m])

    def test_successful_create_and_publish_are_logged_with_their_outcome(self):
        capture = self.capture_logs()

        event = self.create_event()
        self.post(f"/api/events/{event['id']}/publish", headers=ADMIN)

        messages = capture.messages()
        self.assertTrue(any(m.startswith("event created") and "outcome=success" in m for m in messages))
        self.assertTrue(any(m.startswith("event published") and "outcome=success" in m for m in messages))

    def test_a_request_id_is_generated_when_none_is_supplied(self):
        response = self.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response["X-Request-ID"]), 8)

    def test_unsafe_request_id_is_replaced(self):
        response = self.get("/api/health", {"X-Request-ID": "bad id\r\nInjected: yes"})

        self.assertNotIn("Injected", response["X-Request-ID"])

    def test_unexpected_errors_return_a_generic_500_without_internal_details(self):
        boom = RuntimeError("secret internal detail at /srv/app/db.sqlite3")

        with mock.patch("backend.api.views.registrations.register_for_event", side_effect=boom):
            response = self.post("/api/events/EVT-1/registrations")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["code"], "INTERNAL_ERROR")
        self.assertNotIn("secret", response.content.decode())
        self.assertNotIn("Traceback", response.content.decode())

    def test_a_database_failure_returns_a_generic_503_without_database_details(self):
        broken = OperationalError("no such table: events_event")

        with mock.patch("backend.api.views.events.list_published", side_effect=broken):
            response = self.get("/api/events")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "SERVICE_UNAVAILABLE")
        self.assertNotIn("events_event", response.content.decode())

    def test_unknown_api_route_returns_json_404(self):
        response = self.get("/api/nope")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "NOT_FOUND")

    def test_wrong_method_returns_json_405_with_allow_header(self):
        response = self.client.delete("/api/events")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], "METHOD_NOT_ALLOWED")
        self.assertIn("GET", response["Allow"])

    def test_api_responses_carry_security_headers_and_are_not_cached(self):
        response = self.get("/api/events")

        self.assertIn("default-src 'self'", response["Content-Security-Policy"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Cache-Control"], "no-store")
