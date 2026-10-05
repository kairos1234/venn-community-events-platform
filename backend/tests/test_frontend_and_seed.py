from io import StringIO

from django.core.management import call_command

from backend.events.models import Event
from backend.registrations.models import Registration
from backend.tests.helpers import ADMIN, ApiTestCase


class FrontendServingTests(ApiTestCase):
    def test_frontend_files_are_served_by_the_same_app(self):
        for path, content_type in [("/", "text/html"), ("/app.js", "javascript"), ("/styles.css", "text/css")]:
            with self.subTest(path=path):
                response = self.get(path)
                response.close()

                self.assertEqual(response.status_code, 200)
                self.assertIn(content_type, response["Content-Type"])

    def test_every_category_and_the_hero_have_a_photo(self):
        names = ["hero"] + [category.lower() for category in Event.Category.values]
        for name in names:
            with self.subTest(image=name):
                response = self.get(f"/images/{name}.jpg")
                response.close()

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "image/jpeg")

    def test_unknown_file_returns_json_404(self):
        response = self.get("/missing.js")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "NOT_FOUND")


class SeedCommandTests(ApiTestCase):
    def seed(self, *args):
        call_command("seed_demo_data", *args, stdout=StringIO())

    def test_demo_data_is_loaded_with_published_and_pending_events(self):
        self.seed()

        published = self.get("/api/events").json()["events"]
        everything = self.get("/api/admin/events", ADMIN).json()["events"]

        self.assertTrue(published)
        self.assertGreater(len(everything), len(published))
        self.assertTrue(all(e["status"] == "PUBLISHED" for e in published))
        full_soon = next(e for e in published if e["id"] == "EVT-1007")
        self.assertEqual(full_soon["spots_remaining"], 1)

    def test_seeding_twice_does_not_duplicate_anything(self):
        self.seed()
        events, registrations = Event.objects.count(), Registration.objects.count()

        self.seed()

        self.assertEqual(Event.objects.count(), events)
        self.assertEqual(Registration.objects.count(), registrations)

    def test_reset_restores_the_original_demo_data(self):
        self.seed()
        self.post("/api/events/EVT-1007/registrations")  # fills the nearly-full event
        self.assertEqual(self.get("/api/events/EVT-1007").json()["spots_remaining"], 0)

        self.seed("--reset")

        self.assertEqual(self.get("/api/events/EVT-1007").json()["spots_remaining"], 1)
        self.assertEqual(self.get("/api/admin/activity", ADMIN).json()["activity"], [])
