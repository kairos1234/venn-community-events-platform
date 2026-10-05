"""Activity records stand in for real notifications (no email/SMS/push is sent)."""

import logging

from backend.notifications.models import Activity
from backend.request_context import current_request_id

log = logging.getLogger(__name__)


def record_event_published(event_id: str) -> None:
    _record(Activity.Type.EVENT_PUBLISHED, event_id, f"Event {event_id} was published.")


def record_registration_created(event_id: str, registration_id: str) -> None:
    _record(
        Activity.Type.REGISTRATION_CREATED,
        event_id,
        f"Registration {registration_id} was created for event {event_id}.",
    )


def list_recent(limit: int = 50) -> list[Activity]:
    return list(Activity.objects.all()[:limit])


def _record(activity_type: str, event_id: str, message: str) -> None:
    Activity.objects.create(
        type=activity_type, event_id=event_id, message=message, request_id=current_request_id()
    )
    log.info("activity recorded type=%s event_id=%s", activity_type, event_id)
