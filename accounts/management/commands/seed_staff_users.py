"""Seed internal staff users and their NEEPCO tenant memberships.

Staff users live in the public schema; the TenantAccessMiddleware requires an
active UserTenantMembership in the current tenant before an internal user can
view HR surfaces. This command creates the sample staff users (idempotently)
and grants them NEEPCO access so the HR / staff flows can be tested.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import UserTenantMembership
from tenants.models import Client

STAFF = [
    ("a.sharma", "Amit Sharma", "hr_manager"),
    ("r.mehta", "Ramesh Mehta", "recruiter"),
    ("s.iyer", "Sundar Iyer", "reviewer"),
    ("p.das", "Priya Das", "auditor"),
    ("k.nath", "Kabita Nath", "viewer"),
]

STAFF_PASSWORD = "employee123"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
TENANT_SCHEMA = "neepco"


class Command(BaseCommand):
    help = "Create sample staff users and grant them NEEPCO tenant access."

    def handle(self, *args, **options):
        tenant = Client.objects.get(schema_name=TENANT_SCHEMA)
        User = get_user_model()

        created, updated = 0, 0
        for username, full_name, role in STAFF:
            user, was_created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": full_name.split()[0],
                    "last_name": " ".join(full_name.split()[1:]),
                    "email": f"{username}@neepco.co.in",
                    "is_staff": True,
                    "is_active": True,
                },
            )
            if was_created:
                user.set_password(STAFF_PASSWORD)
                user.save()
                created += 1
            else:
                user.is_staff = True
                user.is_active = True
                user.save()
                updated += 1

            membership, membership_created = UserTenantMembership.objects.get_or_create(
                user=user,
                tenant=tenant,
                defaults={"role": role, "is_active": True},
            )
            if not membership_created:
                membership.role = role
                membership.is_active = True
                membership.save()

        # Superuser (organisation admin) — create if missing, never reset password.
        admin, admin_created = User.objects.get_or_create(
            username=ADMIN_USERNAME,
            defaults={
                "email": "admin@neepco.co.in",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        if admin_created:
            admin.set_password(ADMIN_PASSWORD)
            admin.save()
        UserTenantMembership.objects.get_or_create(
            user=admin,
            tenant=tenant,
            defaults={"role": "org_admin", "is_active": True},
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Staff users: {created} created, {updated} updated. "
                f"All granted access to {tenant.name}."
            )
        )
