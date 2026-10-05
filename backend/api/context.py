"""Request helpers: the demo role from headers, and the JSON body."""

import json
import re

from django.core.exceptions import RequestDataTooBig

from backend.errors import PayloadTooLargeError, ValidationError
from backend.roles import ORGANISER, ROLES, VISITOR, Actor

ROLE_HEADER = "X-Demo-Role"
ORGANISER_HEADER = "X-Demo-Organiser-Id"
_ORGANISER_ID = re.compile(r"^[a-z0-9-]{1,40}$")


def current_actor(request) -> Actor:
    role = request.headers.get(ROLE_HEADER, VISITOR).strip().lower()
    if role not in ROLES:
        raise ValidationError("INVALID_ROLE", f"{ROLE_HEADER} must be one of: {', '.join(ROLES)}.")
    if role != ORGANISER:
        return Actor(role)

    organiser_id = request.headers.get(ORGANISER_HEADER, "").strip()
    if not _ORGANISER_ID.match(organiser_id):
        raise ValidationError("INVALID_ORGANISER_ID", f"{ORGANISER_HEADER} is required for the organiser role.")
    return Actor(role, organiser_id)


def json_body(request) -> dict:
    try:
        raw = request.body
    except RequestDataTooBig:
        raise PayloadTooLargeError("PAYLOAD_TOO_LARGE", "The request body is too large.") from None
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):  # bad JSON, bad UTF-8, or absurdly deep nesting
        data = None
    if not isinstance(data, dict):
        raise ValidationError("INVALID_JSON", "Request body must be a JSON object.")
    return data
