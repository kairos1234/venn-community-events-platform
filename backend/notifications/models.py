from django.db import models
from django.utils import timezone


class Activity(models.Model):
    """An activity record that stands in for a real notification (no email/SMS/push is sent)."""

    class Type(models.TextChoices):
        EVENT_PUBLISHED = "EVENT_PUBLISHED"
        REGISTRATION_CREATED = "REGISTRATION_CREATED"

    type = models.CharField(max_length=30, choices=Type.choices)
    event_id = models.CharField(max_length=20)
    message = models.CharField(max_length=255)
    request_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "activity"

    def __str__(self) -> str:
        return self.message
