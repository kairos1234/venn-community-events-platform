"""Fictional demo data. Dates are relative to "now" so seeded events are always upcoming."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from backend.clock import utcnow
from backend.events.models import Event
from backend.notifications.models import Activity
from backend.registrations.models import Registration

PUBLISHED = Event.Status.PUBLISHED
PENDING = Event.Status.PENDING_REVIEW

# (id, title, description, category, days from now, hour, minute, capacity, registered, status, organiser)
SEED_EVENTS = [
    ("EVT-1001", "Tech Meetup",
     "Join us for an evening of networking, talks and great conversations with fellow tech enthusiasts.",
     "Technology", 15, 18, 0, 50, 32, PUBLISHED, "organiser-1"),
    ("EVT-1002", "Community Run",
     "A friendly 5km run for all fitness levels. Meet new people and explore the local trails.",
     "Sports", 20, 8, 0, 100, 76, PUBLISHED, "organiser-2"),
    ("EVT-1003", "Creative Workshop",
     "Explore your creative side in this hands-on art workshop. All materials provided.",
     "Arts", 25, 14, 0, 25, 18, PUBLISHED, "organiser-1"),
    ("EVT-1004", "Community Cleanup",
     "Help make a difference in our local park. Tools and refreshments provided.",
     "Community", 28, 9, 0, 50, 45, PUBLISHED, "organiser-2"),
    ("EVT-1005", "Local Food Market",
     "Support local vendors and enjoy great food, crafts and live music.",
     "Food", 34, 10, 0, 150, 120, PUBLISHED, "organiser-1"),
    ("EVT-1006", "Hiking Adventure",
     "A guided hike with stunning views and like-minded nature lovers.",
     "Nature", 41, 7, 0, 30, 22, PUBLISHED, "organiser-2"),
    # Nearly full on purpose: two more registrations demonstrate the capacity rule.
    ("EVT-1007", "Poetry Open Mic",
     "Share a poem or simply listen. A relaxed evening for words and good company.",
     "Arts", 10, 19, 0, 3, 2, PUBLISHED, "organiser-2"),
    # Awaiting review: not visible to Visitors until an administrator publishes them.
    ("EVT-1008", "Neighbourhood Book Swap",
     "Bring a book, take a book. Tea and coffee provided.",
     "Community", 18, 11, 0, 40, 0, PENDING, "organiser-1"),
    ("EVT-1009", "Sunset Yoga in the Park",
     "A gentle open-air yoga session for beginners. Bring your own mat.",
     "Sports", 12, 17, 30, 20, 0, PENDING, "organiser-2"),
    ("EVT-1010", "Intro to Python Night",
     "A beginner-friendly evening of small coding exercises and friendly help.",
     "Technology", 22, 18, 30, 30, 0, PENDING, "organiser-1"),
]


class Command(BaseCommand):
    help = "Load fictional demo events (only when the database has no events yet)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete all events, registrations and activity first, then load the demo data.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            Activity.objects.all().delete()
            Event.objects.all().delete()  # registrations are removed with their event

        if Event.objects.exists():
            self.stdout.write("The database already contains events; nothing to seed (use --reset to start over).")
            return

        now = utcnow()
        for (event_id, title, description, category, days, hour, minute,
             capacity, registered, status, organiser_id) in SEED_EVENTS:
            starts_at = (now + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            event = Event.objects.create(
                id=event_id, title=title, description=description, category=category,
                starts_at=starts_at, capacity=capacity, status=status, organiser_id=organiser_id,
            )
            Registration.objects.bulk_create([Registration(event=event) for _ in range(registered)])

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(SEED_EVENTS)} demo events."))
