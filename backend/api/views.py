import logging

from django.db import OperationalError, connection
from django.http import JsonResponse
from django.views import View

from backend.api.context import current_actor, json_body
from backend.clock import to_iso
from backend.errors import AppError
from backend.events import services as events
from backend.events.serializers import event_to_dict
from backend.notifications import services as notifications
from backend.registrations import services as registrations
from backend.roles import ADMIN, ORGANISER, require_role

log = logging.getLogger(__name__)


class ApiView(View):
    """Base class: turns expected errors into `{"code", "message"}` JSON and hides unexpected ones."""

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except AppError as err:
            # Log the outcome of every rejected request. Only error codes and field *names* are
            # logged, never submitted values, so no user-entered text ends up in the logs.
            fields = f" fields={','.join(err.fields)}" if err.fields else ""
            log.warning("request rejected method=%s path=%s status=%d code=%s%s",
                        request.method, request.path, err.status, err.code, fields)
            return JsonResponse(err.to_dict(), status=err.status)
        except OperationalError:
            # Database not ready (e.g. `migrate` not run yet) or locked for too long. The client gets a
            # generic 503; the log says what to check.
            log.exception("database unavailable method=%s path=%s (if tables are missing, run: python manage.py migrate)",
                          request.method, request.path)
            return JsonResponse(
                {"code": "SERVICE_UNAVAILABLE", "message": "The service is temporarily unavailable. Please try again shortly."},
                status=503,
            )
        except Exception:
            # Full details (with traceback) go to the server log only, never to the client.
            log.exception("unhandled error method=%s path=%s", request.method, request.path)
            return JsonResponse(
                {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred. Please try again later."},
                status=500,
            )

    def http_method_not_allowed(self, request, *args, **kwargs):
        response = JsonResponse(
            {"code": "METHOD_NOT_ALLOWED", "message": "This method is not allowed for the requested resource."},
            status=405,
        )
        response["Allow"] = ", ".join(self._allowed_methods())
        return response


class HealthView(ApiView):
    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})


# --- Visitor: browse published events and register interest -----------------

class EventCollectionView(ApiView):
    def get(self, request):
        upcoming = request.GET.get("upcoming", "").lower() in ("1", "true", "yes")
        found = events.list_published(request.GET.get("category"), upcoming)
        return JsonResponse({"events": [event_to_dict(e) for e in found]})

    # --- Organiser: create ---
    def post(self, request):
        actor = current_actor(request)
        require_role(actor, ORGANISER)
        event = events.create_event(json_body(request), actor)
        response = JsonResponse(event_to_dict(event), status=201)
        response["Location"] = f"/api/events/{event.id}"
        return response


class EventDetailView(ApiView):
    def get(self, request, event_id):
        return JsonResponse(event_to_dict(events.get_event(event_id, current_actor(request))))

    # --- Organiser: update their own event ---
    def put(self, request, event_id):
        actor = current_actor(request)
        require_role(actor, ORGANISER)
        return JsonResponse(event_to_dict(events.update_event(event_id, json_body(request), actor)))

        # --- Administrator: delete event ---
    def delete(self, request, event_id):
        require_role(current_actor(request), ADMIN)
        events.delete_event(event_id)
        return JsonResponse({"message": "Event deleted successfully."})
class EventRegistrationsView(ApiView):
    def post(self, request, event_id):
        registration = registrations.register_for_event(event_id)
        return JsonResponse(
            {
                "id": registration.id,
                "event_id": registration.event_id,
                "registered_at": to_iso(registration.registered_at),
            },
            status=201,
        )


# --- Organiser: their own events --------------------------------------------

class OrganiserEventsView(ApiView):
    def get(self, request):
        actor = current_actor(request)
        require_role(actor, ORGANISER)
        return JsonResponse({"events": [event_to_dict(e) for e in events.list_for_organiser(actor)]})


# --- Administrator: review, publish, and see activity -----------------------

class AdminEventsView(ApiView):
    def get(self, request):
        require_role(current_actor(request), ADMIN)
        found = events.list_for_admin(request.GET.get("status"))
        return JsonResponse({"events": [event_to_dict(e) for e in found]})


class EventPublishView(ApiView):
    def post(self, request, event_id):
        require_role(current_actor(request), ADMIN)
        return JsonResponse(event_to_dict(events.publish_event(event_id)))



class AdminActivityView(ApiView):
    def get(self, request):
        require_role(current_actor(request), ADMIN)
        return JsonResponse(
            {
                "activity": [
                    {
                        "id": a.id,
                        "type": a.type,
                        "event_id": a.event_id,
                        "message": a.message,
                        "request_id": a.request_id,
                        "created_at": to_iso(a.created_at),
                    }
                    for a in notifications.list_recent()
                ]
            }
        )
