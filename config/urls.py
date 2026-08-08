"""Root URL configuration for TalentFlow AI."""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.i18n import JavaScriptCatalog

# Friendly access-denied page for PermissionDenied raised by @require_role.
handler403 = "accounts.views.access_denied"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),
    path("", include("recruitment.urls")),
    path("", include("accounts.urls")),
    path("", include("portal.urls")),
    path("", include("profiles.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
