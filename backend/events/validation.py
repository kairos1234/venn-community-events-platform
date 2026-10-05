import unicodedata
from datetime import datetime, timezone

from backend.errors import ValidationError
from backend.events.models import Event

TITLE_MAX = 120
DESCRIPTION_MAX = 2000
CAPACITY_MAX = 100_000


def validate_event_payload(
    payload: dict,
    now: datetime,
    existing_starts_at: datetime | None = None,
    min_capacity: int = 1,
) -> dict:
    """Validate and normalise an event create/update body.

    - `existing_starts_at`: on update, an unchanged date is not re-checked against
      "now", so editing the title of an event that has since started still works.
    - `min_capacity`: on update, capacity cannot drop below existing registrations.
    """
    problems: dict[str, str] = {}

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        problems["title"] = "Title is required."
    elif len(title.strip()) > TITLE_MAX:
        problems["title"] = f"Title must be at most {TITLE_MAX} characters."
    elif _has_unsafe_chars(title):
        problems["title"] = "Title must not contain control characters."

    description = payload.get("description", "")
    if description is None:
        description = ""
    if not isinstance(description, str):
        problems["description"] = "Description must be text."
    elif len(description) > DESCRIPTION_MAX:
        problems["description"] = f"Description must be at most {DESCRIPTION_MAX} characters."
    elif _has_unsafe_chars(description, allowed="\n\r\t"):
        problems["description"] = "Description must not contain control characters."

    category = payload.get("category", Event.Category.COMMUNITY)
    if category not in Event.Category.values:
        problems["category"] = f"Category must be one of: {', '.join(Event.Category.values)}."

    starts_at = _parse_starts_at(payload.get("starts_at"))
    if starts_at is None:
        problems["starts_at"] = "Date and time is required and must be a valid ISO 8601 date-time."
    elif starts_at < now and starts_at != existing_starts_at:
        problems["starts_at"] = "Date and time must not be in the past."

    capacity = payload.get("capacity")
    # bool is a subclass of int in Python, so exclude it explicitly.
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
        problems["capacity"] = "Capacity must be a whole number greater than zero."
    elif capacity > CAPACITY_MAX:
        problems["capacity"] = f"Capacity must be at most {CAPACITY_MAX}."
    elif capacity < min_capacity:
        problems["capacity"] = f"Capacity cannot be lower than the {min_capacity} registrations already made."

    if problems:
        raise ValidationError("VALIDATION_ERROR", " ".join(problems.values()), fields=problems)

    return {
        "title": title.strip(),
        "description": description.strip(),
        "category": category,
        "starts_at": starts_at,
        "capacity": capacity,
    }


def _has_unsafe_chars(text: str, allowed: str = "") -> bool:
    """Control characters and lone surrogates are never valid text (the database cannot store the latter)."""
    return any(unicodedata.category(ch) in ("Cc", "Cs") and ch not in allowed for ch in text)


def _parse_starts_at(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
        if parsed.tzinfo is None:  # a date-time without an offset is treated as UTC
            parsed = parsed.replace(tzinfo=timezone.utc)
        # OverflowError: e.g. 0001-01-01T00:00:00+14:00 has no UTC equivalent inside datetime's range.
        return parsed.astimezone(timezone.utc).replace(microsecond=0)
    except (ValueError, OverflowError):
        return None
