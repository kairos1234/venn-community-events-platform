from django.db import models
from django.utils import timezone

from backend.clock import new_id


def new_registration_id() -> str:
    return new_id("REG")


class Registration(models.Model):
    """Anonymous interest in an event.

    Deliberately holds only a generated ID, the event, and a timestamp: no names,
    emails, IP addresses, device details or free text (brief section 3.3).
    """

    id = models.CharField(primary_key=True, max_length=20, default=new_registration_id, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="registrations")
    registered_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"{self.id} for {self.event_id}"
