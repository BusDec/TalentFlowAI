"""Internal HR/staff user models — live in the public schema."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Internal platform user (HR, recruiter, reviewer, auditor, admin)."""

    employee_id = models.CharField(max_length=50, blank=True, null=True)
    mobile = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return self.get_full_name() or self.username


class UserTenantMembership(models.Model):
    """Links a user to one or more tenants with a role."""

    ROLE_CHOICES = (
        ("super_admin", "Super Admin"),
        ("org_admin", "Organisation Admin"),
        ("hr_manager", "HR Manager"),
        ("recruiter", "Recruiter"),
        ("reviewer", "Reviewer"),
        ("auditor", "Auditor"),
        ("viewer", "Viewer"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tenant_memberships")
    tenant = models.ForeignKey("tenants.Client", on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default="viewer")
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "tenant")
        verbose_name = "User Tenant Membership"

    def __str__(self):
        return f"{self.user} → {self.tenant} ({self.role})"
