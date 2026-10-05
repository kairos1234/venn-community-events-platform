from backend.clock import to_iso
from backend.events.models import Event


def event_to_dict(event: Event) -> dict:
    registered = getattr(event, "registration_count", None)
    if registered is None:  # instance did not come from `with_registration_count()`
        registered = event.registrations.count()
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "category": event.category,
        "starts_at": to_iso(event.starts_at),
        "capacity": event.capacity,
        "registration_count": registered,
        "spots_remaining": max(event.capacity - registered, 0),
        "status": event.status,
        "organiser_id": event.organiser_id,
        "created_at": to_iso(event.created_at),
        "updated_at": to_iso(event.updated_at),
    }
