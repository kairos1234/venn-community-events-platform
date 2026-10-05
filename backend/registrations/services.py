import logging

from django.db import transaction

from backend.clock import utcnow
from backend.errors import ConflictError, NotFoundError
from backend.events.models import Event
from backend.notifications import services as notifications
from backend.registrations.models import Registration

log = logging.getLogger(__name__)


def register_for_event(event_id: str) -> Registration:
    """Record anonymous interest in a published event that has not started and still has room.

    The checks and the insert share one transaction that holds the write lock (row lock via
    `select_for_update`, plus IMMEDIATE mode on SQLite), so two people registering for the
    last spot cannot both succeed.
    """
    log.info("registration requested event_id=%s", event_id)
    with transaction.atomic():
        try:
            event = Event.objects.select_for_update().get(pk=event_id)
        except Event.DoesNotExist:
            log.warning("registration rejected event_id=%s outcome=EVENT_NOT_FOUND", event_id)
            raise NotFoundError("EVENT_NOT_FOUND", "Event not found.") from None

        if event.status != Event.Status.PUBLISHED:
            log.warning("registration rejected event_id=%s outcome=EVENT_NOT_PUBLISHED", event_id)
            raise ConflictError(
                "EVENT_NOT_PUBLISHED", "Registration is not available because this event is not published."
            )
        if event.starts_at <= utcnow():
            log.warning("registration rejected event_id=%s outcome=REGISTRATION_CLOSED", event_id)
            raise ConflictError("REGISTRATION_CLOSED", "Registration is closed because this event has already started.")
        taken = event.registrations.count()
        if taken >= event.capacity:
            log.warning("registration rejected event_id=%s outcome=EVENT_FULL", event_id)
            raise ConflictError("EVENT_FULL", "Registration is no longer available because this event is full.")
        log.info("event validated event_id=%s spots_remaining=%d", event_id, event.capacity - taken)

        registration = Registration.objects.create(event=event)
        log.info("registration stored registration_id=%s event_id=%s", registration.id, event_id)
        notifications.record_registration_created(event_id, registration.id)

    log.info("registration completed registration_id=%s event_id=%s outcome=success", registration.id, event_id)
    return registration
