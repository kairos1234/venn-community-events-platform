import logging

from django.db import transaction

from backend.clock import utcnow
from backend.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from backend.events.models import Event
from backend.events.validation import validate_event_payload
from backend.notifications import services as notifications
from backend.roles import ADMIN, ORGANISER, Actor

log = logging.getLogger(__name__)


def create_event(payload: dict, actor: Actor) -> Event:
    data = validate_event_payload(payload, utcnow())
    event = Event.objects.create(**data, status=Event.Status.PENDING_REVIEW, organiser_id=actor.organiser_id)
    log.info("event created event_id=%s organiser_id=%s status=%s outcome=success",
             event.id, actor.organiser_id, event.status)
    return _fetch(event.id)


def update_event(event_id: str, payload: dict, actor: Actor) -> Event:
    with transaction.atomic():
        event = _lock_or_404(event_id)
        if event.organiser_id != actor.organiser_id:
            log.warning("event update denied event_id=%s organiser_id=%s", event_id, actor.organiser_id)
            raise ForbiddenError("FORBIDDEN", "You can only update events that you manage.")
        data = validate_event_payload(
            payload,
            utcnow(),
            existing_starts_at=event.starts_at,
            min_capacity=event.registrations.count(),
        )
        for field, value in data.items():
            setattr(event, field, value)
        event.save(update_fields=[*data, "updated_at"])
    log.info("event updated event_id=%s organiser_id=%s outcome=success", event_id, actor.organiser_id)
    return _fetch(event_id)


def publish_event(event_id: str) -> Event:
    with transaction.atomic():
        event = _lock_or_404(event_id)
        if event.status != Event.Status.PENDING_REVIEW:
            log.warning("publish rejected event_id=%s status=%s", event_id, event.status)
            raise ConflictError("EVENT_NOT_PENDING_REVIEW", f"Event {event_id} is not awaiting review.")
        event.status = Event.Status.PUBLISHED
        event.save(update_fields=["status", "updated_at"])
        # Same transaction as the status change: an event is never published without its activity entry.
        notifications.record_event_published(event_id)
    log.info("event published event_id=%s outcome=success", event_id)
    return _fetch(event_id)

def delete_event(event_id: str) -> None:
    with transaction.atomic():
        event = _lock_or_404(event_id)
        event.delete()

    log.info("event deleted event_id=%s outcome=success", event_id)

def get_event(event_id: str, actor: Actor) -> Event:
    event = Event.objects.with_registration_count().filter(pk=event_id).first()
    # Hidden events look exactly like missing ones, so unpublished IDs cannot be probed.
    if event is None or not _can_view(event, actor):
        raise NotFoundError("EVENT_NOT_FOUND", "Event not found.")
    return event


def list_published(category: str | None = None, upcoming_only: bool = False) -> list[Event]:
    if category is not None and category not in Event.Category.values:
        raise ValidationError("VALIDATION_ERROR", f"Category must be one of: {', '.join(Event.Category.values)}.")
    events = Event.objects.with_registration_count().filter(status=Event.Status.PUBLISHED)
    if category is not None:
        events = events.filter(category=category)
    if upcoming_only:
        events = events.filter(starts_at__gte=utcnow())
    return list(events)


def list_for_organiser(actor: Actor) -> list[Event]:
    return list(Event.objects.with_registration_count().filter(organiser_id=actor.organiser_id))


def list_for_admin(status: str | None = None) -> list[Event]:
    if status is not None and status not in Event.Status.values:
        raise ValidationError("VALIDATION_ERROR", "Status must be PENDING_REVIEW or PUBLISHED.")
    events = Event.objects.with_registration_count()
    if status is not None:
        events = events.filter(status=status)
    return list(events)


def _fetch(event_id: str) -> Event:
    return Event.objects.with_registration_count().get(pk=event_id)


def _lock_or_404(event_id: str) -> Event:
    """Fetch an event for modification. Must be called inside `transaction.atomic()`.

    `select_for_update` locks the row on databases that support it; on SQLite it is a no-op
    and the IMMEDIATE transaction mode (see settings) provides the write lock instead.
    """
    try:
        return Event.objects.select_for_update().get(pk=event_id)
    except Event.DoesNotExist:
        raise NotFoundError("EVENT_NOT_FOUND", "Event not found.") from None


def _can_view(event: Event, actor: Actor) -> bool:
    if event.status == Event.Status.PUBLISHED or actor.role == ADMIN:
        return True
    return actor.role == ORGANISER and event.organiser_id == actor.organiser_id
