from datetime import datetime, timezone

from django.db import IntegrityError, transaction

from backend.events.models import Event
from backend.tests.helpers import (
    ADMIN,
    ORGANISER_1,
    ORGANISER_2,
    VISITOR,
    ApiTestCase,
    event_payload,
    future_date,
)

LONG_AGO = datetime(2000, 1, 1, 10, 0, tzinfo=timezone.utc)


class EventValidationTests(ApiTestCase):
    def test_invalid_event_is_rejected_with_400(self):
        cases = [
            ({"title": ""}, "title"),
            ({"title": "   "}, "title"),
            ({"title": None}, "title"),
            ({"title": "x" * 121}, "title"),
            ({"capacity": 0}, "capacity"),
            ({"capacity": -5}, "capacity"),
            ({"capacity": 2.5}, "capacity"),
            ({"capacity": "10"}, "capacity"),
            ({"capacity": True}, "capacity"),
            ({"starts_at": ""}, "starts_at"),
            ({"starts_at": "not-a-date"}, "starts_at"),
            ({"starts_at": "2000-01-01T10:00:00Z"}, "starts_at"),
            ({"category": "Gambling"}, "category"),
            # Dates with no UTC equivalent inside Python's date range used to crash with a 500.
            ({"starts_at": "0001-01-01T00:00:00+14:00"}, "starts_at"),
            ({"starts_at": "9999-12-31T23:59:59-14:00"}, "starts_at"),
            # Control characters and lone surrogates (which the database cannot store) are rejected.
            ({"title": "a\u0000b"}, "title"),
            ({"title": "bad \ud800 text"}, "title"),
            ({"description": "bad \udc00 text"}, "description"),
        ]
        for overrides, field in cases:
            with self.subTest(overrides=overrides):
                response = self.post("/api/events", event_payload(**overrides), ORGANISER_1)

                self.assertEqual(response.status_code, 400)
                body = response.json()
                self.assertEqual(body["code"], "VALIDATION_ERROR")
                self.assertIn(field, body["fields"])
        self.assertEqual(Event.objects.count(), 0)

    def test_malformed_json_body_is_rejected_with_400(self):
        response = self.client.post(
            "/api/events", data="{not json", content_type="application/json", headers=ORGANISER_1
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_JSON")

    def test_absurdly_nested_json_is_rejected_with_400_not_a_server_error(self):
        response = self.client.post(
            "/api/events", data="[" * 30_000 + "]" * 30_000, content_type="application/json", headers=ORGANISER_1
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_JSON")

    def test_multiline_descriptions_are_still_allowed(self):
        event = self.create_event(description="Line one\n\tLine two")

        self.assertEqual(event["description"], "Line one\n\tLine two")

    def test_oversized_body_is_rejected_with_413(self):
        response = self.post("/api/events", event_payload(description="x" * 70_000), ORGANISER_1)

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["code"], "PAYLOAD_TOO_LARGE")

    def test_database_itself_rejects_zero_capacity(self):
        # Defence in depth: even code that bypasses the API validation cannot store capacity 0.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Event.objects.create(title="Bad", starts_at=LONG_AGO, capacity=0, organiser_id="organiser-1")


class EventLifecycleTests(ApiTestCase):
    def test_new_event_is_pending_review_and_hidden_from_visitors(self):
        event = self.create_event()

        self.assertEqual(event["status"], "PENDING_REVIEW")
        self.assertEqual(event["organiser_id"], "organiser-1")
        self.assertEqual(self.get("/api/events", VISITOR).json()["events"], [])
        self.assertEqual(self.get(f"/api/events/{event['id']}", VISITOR).status_code, 404)
        # The owning organiser and administrators can still see it; another organiser cannot.
        self.assertEqual(self.get(f"/api/events/{event['id']}", ORGANISER_1).status_code, 200)
        self.assertEqual(self.get(f"/api/events/{event['id']}", ADMIN).status_code, 200)
        self.assertEqual(self.get(f"/api/events/{event['id']}", ORGANISER_2).status_code, 404)

    def test_organiser_cannot_self_publish_or_change_ownership_through_the_request_body(self):
        sneaky = event_payload(status="PUBLISHED", organiser_id="organiser-2", id="EVT-HACKED")

        created = self.post("/api/events", sneaky, ORGANISER_1).json()
        updated = self.put(f"/api/events/{created['id']}", sneaky, ORGANISER_1).json()

        for event in (created, updated):
            self.assertEqual(event["status"], "PENDING_REVIEW")
            self.assertEqual(event["organiser_id"], "organiser-1")
            self.assertNotEqual(event["id"], "EVT-HACKED")
        self.assertEqual(self.get("/api/events", VISITOR).json()["events"], [])

    def test_publishing_makes_event_visible_and_records_activity(self):
        event = self.create_event()

        response = self.post(f"/api/events/{event['id']}/publish", headers=ADMIN)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "PUBLISHED")
        visible = self.get("/api/events", VISITOR).json()["events"]
        self.assertEqual([e["id"] for e in visible], [event["id"]])
        activity = self.get("/api/admin/activity", ADMIN).json()["activity"]
        self.assertEqual(activity[0]["message"], f"Event {event['id']} was published.")

    def test_only_administrators_can_publish(self):
        event = self.create_event()

        self.assertEqual(self.post(f"/api/events/{event['id']}/publish", headers=VISITOR).status_code, 403)
        self.assertEqual(self.post(f"/api/events/{event['id']}/publish", headers=ORGANISER_1).status_code, 403)
        self.assertEqual(self.get(f"/api/events/{event['id']}", VISITOR).status_code, 404)

    def test_publishing_twice_is_a_conflict_and_records_one_activity_entry(self):
        event = self.create_published_event()

        response = self.post(f"/api/events/{event['id']}/publish", headers=ADMIN)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "EVENT_NOT_PENDING_REVIEW")
        self.assertEqual(len(self.get("/api/admin/activity", ADMIN).json()["activity"]), 1)

    def test_publishing_unknown_event_is_404(self):
        response = self.post("/api/events/EVT-NOPE/publish", headers=ADMIN)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "EVENT_NOT_FOUND")


class EventUpdateTests(ApiTestCase):
    def test_organiser_can_update_own_event_but_not_anothers(self):
        event = self.create_event()

        ok = self.put(f"/api/events/{event['id']}", event_payload(title="Renamed", capacity=25), ORGANISER_1)
        denied = self.put(f"/api/events/{event['id']}", event_payload(title="Hijacked"), ORGANISER_2)

        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["title"], "Renamed")
        self.assertEqual(ok.json()["capacity"], 25)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.get(f"/api/events/{event['id']}", ORGANISER_1).json()["title"], "Renamed")

    def test_capacity_cannot_be_lowered_below_existing_registrations(self):
        event = self.create_published_event(capacity=5)
        for _ in range(3):
            self.post(f"/api/events/{event['id']}/registrations")

        response = self.put(f"/api/events/{event['id']}", event_payload(capacity=2), ORGANISER_1)

        self.assertEqual(response.status_code, 400)
        self.assertIn("capacity", response.json()["fields"])

    def test_unchanged_past_date_is_allowed_when_updating_other_fields(self):
        event = self.create_event(starts_at=future_date(1))
        # Simulate the event's start time passing while it is still being managed.
        Event.objects.filter(pk=event["id"]).update(starts_at=LONG_AGO)

        unchanged = self.put(
            f"/api/events/{event['id']}",
            event_payload(title="Still editable", starts_at="2000-01-01T10:00:00Z"),
            ORGANISER_1,
        )
        moved_to_past = self.put(
            f"/api/events/{event['id']}", event_payload(starts_at="1999-01-01T10:00:00Z"), ORGANISER_1
        )

        self.assertEqual(unchanged.status_code, 200)
        self.assertEqual(moved_to_past.status_code, 400)


class EventListingTests(ApiTestCase):
    def test_organiser_list_only_contains_own_events_and_admin_list_contains_all(self):
        mine = self.create_event(headers=ORGANISER_1, title="Mine")
        theirs = self.create_event(headers=ORGANISER_2, title="Theirs")

        own = self.get("/api/organiser/events", ORGANISER_1).json()["events"]
        everything = self.get("/api/admin/events", ADMIN).json()["events"]

        self.assertEqual([e["id"] for e in own], [mine["id"]])
        self.assertEqual({e["id"] for e in everything}, {mine["id"], theirs["id"]})
        self.assertEqual(self.get("/api/admin/events", VISITOR).status_code, 403)
        self.assertEqual(self.get("/api/organiser/events", VISITOR).status_code, 403)

    def test_admin_list_can_filter_by_status(self):
        self.create_event(title="Pending")
        published = self.create_published_event(title="Live")

        only_published = self.get("/api/admin/events?status=PUBLISHED", ADMIN).json()["events"]

        self.assertEqual([e["id"] for e in only_published], [published["id"]])
        self.assertEqual(self.get("/api/admin/events?status=NOPE", ADMIN).status_code, 400)

    def test_visitor_listing_can_filter_by_category(self):
        self.create_published_event(title="Run", category="Sports")
        self.create_published_event(title="Code", category="Technology")

        sports = self.get("/api/events?category=Sports").json()["events"]

        self.assertEqual([e["title"] for e in sports], ["Run"])
        self.assertEqual(self.get("/api/events?category=Nope").status_code, 400)

    def test_upcoming_filter_hides_events_that_have_started(self):
        past = self.create_published_event(title="Past")
        self.create_published_event(title="Future")
        Event.objects.filter(pk=past["id"]).update(starts_at=LONG_AGO)

        everything = self.get("/api/events").json()["events"]
        upcoming = self.get("/api/events?upcoming=true").json()["events"]

        self.assertEqual({e["title"] for e in everything}, {"Past", "Future"})
        self.assertEqual([e["title"] for e in upcoming], ["Future"])


class DemoRoleTests(ApiTestCase):
    def test_organiser_role_requires_an_identifier(self):
        response = self.post("/api/events", event_payload(), {"X-Demo-Role": "organiser"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_ORGANISER_ID")

    def test_unknown_role_is_rejected(self):
        response = self.get("/api/events/EVT-1", {"X-Demo-Role": "superuser"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_ROLE")

    def test_event_text_is_returned_verbatim_as_json_not_html(self):
        event = self.create_event(title="<script>alert(1)</script>")

        response = self.get(f"/api/events/{event['id']}", ORGANISER_1)

        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json()["title"], "<script>alert(1)</script>")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
