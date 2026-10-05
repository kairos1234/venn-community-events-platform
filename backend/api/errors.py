"""JSON error responses for failures Django raises itself (unknown URL, bad Host header, ...).

Errors raised inside API views are handled in `views.ApiView.dispatch`. Both use the same
`{"code", "message"}` shape and never include stack traces, SQL, paths or settings.
"""

from django.http import JsonResponse


def _error(status: int, code: str, message: str) -> JsonResponse:
    return JsonResponse({"code": code, "message": message}, status=status)


def bad_request(request, exception=None):
    return _error(400, "BAD_REQUEST", "The request could not be processed.")


def forbidden(request, exception=None):
    return _error(403, "FORBIDDEN", "You do not have permission to do that.")


def not_found(request, exception=None):
    return _error(404, "NOT_FOUND", "The requested resource was not found.")


def server_error(request):
    return _error(500, "INTERNAL_ERROR", "An unexpected error occurred. Please try again later.")
