import uuid
from datetime import datetime, timezone

from django.utils import timezone as dj_timezone

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utcnow() -> datetime:
    return dj_timezone.now()


def to_iso(moment: datetime) -> str:
    """The API always returns UTC ISO-8601 timestamps such as 2026-11-20T18:00:00Z."""
    return moment.astimezone(timezone.utc).strftime(ISO_FORMAT)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
