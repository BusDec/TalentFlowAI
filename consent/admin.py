from django.contrib import admin
from .models import Consent, ConsentEvent


class ConsentEventInline(admin.TabularInline):
    model = ConsentEvent
    extra = 0
    readonly_fields = ("timestamp",)
    can_delete = False


@admin.register(Consent)
class ConsentAdmin(admin.ModelAdmin):
    list_display = ("candidate_portal_user", "purpose", "granted_at", "expires_at", "revoked_at", "is_active")
    list_filter = ("purpose", "revoked_at")
    search_fields = ("candidate_portal_user__email",)
    inlines = [ConsentEventInline]


@admin.register(ConsentEvent)
class ConsentEventAdmin(admin.ModelAdmin):
    list_display = ("consent", "action", "actor", "timestamp")
    list_filter = ("action",)
    search_fields = ("consent__candidate_portal_user__email",)
    readonly_fields = ("timestamp",)
