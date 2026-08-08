from django.contrib import admin
from .models import CandidatePortalUser


@admin.register(CandidatePortalUser)
class CandidatePortalUserAdmin(admin.ModelAdmin):
    list_display = ("email", "full_name", "phone", "otp_verified", "is_active", "date_joined")
    list_filter = ("otp_verified", "is_active")
    search_fields = ("email", "full_name", "phone")
