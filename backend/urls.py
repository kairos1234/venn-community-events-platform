from django.conf import settings
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("api/", include("backend.api.urls")),
    # The frontend is plain static files served by this same app.
    path("", serve, {"path": "index.html", "document_root": settings.FRONTEND_DIR}),
    re_path(r"^(?P<path>(?:images/)?[\w.\-]+)$", serve, {"document_root": settings.FRONTEND_DIR}),
]

# JSON bodies for errors Django raises itself (unknown URL, bad Host header, ...).
handler400 = "backend.api.errors.bad_request"
handler403 = "backend.api.errors.forbidden"
handler404 = "backend.api.errors.not_found"
handler500 = "backend.api.errors.server_error"
