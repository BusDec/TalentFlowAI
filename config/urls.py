"""Root URL configuration for TalentFlow AI."""

import json

from django.contrib import admin
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, include, reverse
from django.conf import settings
from django.conf.urls.static import static
from django.views.i18n import JavaScriptCatalog

# Friendly access-denied page for PermissionDenied raised by @require_role.
handler403 = "accounts.views.access_denied"


def _health(request):
    """Lightweight health check — no DB, no tenant lookup."""
    return HttpResponse(
        json.dumps({"status": "ok"}),
        content_type="application/json",
    )


def _root(request):
    """Public root: authenticated staff → dashboard, anonymous → landing."""
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse("dashboard"))
    return HttpResponseRedirect("/landing/")


def _landing(request):
    from config.views import landing_page
    return landing_page(request)


urlpatterns = [
    path("health/", _health, name="health"),
    path("landing/", _landing, name="landing"),
    path("admin/", admin.site.urls),
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),
    path("", _root, name="root"),
    path("", include("recruitment.urls")),
    path("", include("accounts.urls")),
    path("", include("portal.urls")),
    path("", include("profiles.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
