from django.db import models
from django.db.models import Count, Q

from backend.clock import new_id


def new_event_id() -> str:
    return new_id("EVT")


class EventQuerySet(models.QuerySet):
    def with_registration_count(self):
        # Counted from the registrations table, never stored, so it cannot drift out of sync.
        return self.annotate(registration_count=Count("registrations"))


class Event(models.Model):
    class Status(models.TextChoices):
        PENDING_REVIEW = "PENDING_REVIEW", "Pending review"
        PUBLISHED = "PUBLISHED", "Published"

    class Category(models.TextChoices):
        COMMUNITY = "Community"
        TECHNOLOGY = "Technology"
        SPORTS = "Sports"
        ARTS = "Arts"
        FOOD = "Food"
        NATURE = "Nature"

    id = models.CharField(primary_key=True, max_length=20, default=new_event_id, editable=False)
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.COMMUNITY)
    starts_at = models.DateTimeField()  # stored in UTC
    capacity = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_REVIEW)
    organiser_id = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["starts_at", "id"]
        indexes = [models.Index(fields=["status", "starts_at"])]
        constraints = [
            models.CheckConstraint(condition=Q(capacity__gt=0), name="event_capacity_positive"),
            models.CheckConstraint(condition=Q(status__in=["PENDING_REVIEW", "PUBLISHED"]), name="event_status_valid"),
        ]

    def __str__(self) -> str:
        return f"{self.id} {self.title}"
