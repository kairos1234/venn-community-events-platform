"""Demo-only role handling.

There is no authentication. The frontend's role selector sends the chosen role
(and organiser identifier) as request headers and the backend trusts them.
Server-side checks still enforce what each role may do.
"""

from dataclasses import dataclass

from backend.errors import ForbiddenError

VISITOR = "visitor"
ORGANISER = "organiser"
ADMIN = "admin"
ROLES = (VISITOR, ORGANISER, ADMIN)

_ROLE_LABELS = {ORGANISER: "Organiser", ADMIN: "Administrator"}


@dataclass(frozen=True)
class Actor:
    role: str = VISITOR
    organiser_id: str | None = None


def require_role(actor: Actor, role: str) -> None:
    if actor.role != role:
        label = _ROLE_LABELS.get(role, role)
        raise ForbiddenError("FORBIDDEN", f"This action requires the {label} role.")
