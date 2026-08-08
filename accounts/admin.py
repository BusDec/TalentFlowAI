from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, UserTenantMembership


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "employee_id", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("Extra", {"fields": ("employee_id", "mobile")}),
    )


@admin.register(UserTenantMembership)
class UserTenantMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "is_active", "joined_at")
    list_filter = ("role", "is_active", "tenant")
