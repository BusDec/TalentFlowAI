"""Admin registration for notification models."""

from django.contrib import admin

from .models import NotificationOutbox, NotificationTemplate


@admin.register(NotificationOutbox)
class NotificationOutboxAdmin(admin.ModelAdmin):
    list_display = ("channel", "to", "subject", "status", "created_at")
    list_filter = ("status", "channel")
    search_fields = ("to", "subject", "body")
    readonly_fields = ("created_at",)


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "channel", "subject")
    search_fields = ("name",)
