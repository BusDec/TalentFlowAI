"""Seed candidate portal users for the public demo.

Creates the five sample candidate accounts documented in TALENTFLOW_GUIDE.md,
links them to Candidate rows, gives them a few applications and DPDP consent
records, and leaves their profiles for the portal onboarding flow to fill in.

Idempotent — safe to re-run.
"""

from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from django_tenants.utils import schema_context

PORTAL_USERS = [
    ("rahul.sharma@example.com", "Rahul Sharma", "9876500001"),
    ("sneha.reddy@example.com", "Sneha Reddy", "9876500002"),
    ("arjun.patel@example.com", "Arjun Patel", "9876500003"),
    ("priya.sharma@example.com", "Priya Sharma", "9876500004"),
    ("vikram.singh@example.com", "Vikram Singh", "9876500005"),
]

STATUSES = ["received", "shortlisted", "interview", "offered"]


class Command(BaseCommand):
    help = "Create demo candidate portal users, applications and consents."

    def handle(self, *args, **options):
        schema_name = settings.DEMO_TENANT_SCHEMA
        connection.set_schema_to_public()
        with schema_context(schema_name):
            self._seed()

    def _seed(self):
        from consent.models import Consent
        from portal.models import CandidatePortalUser
        from recruitment.models import Application, Candidate, Post

        posts = list(Post.objects.order_by("id")[:6])
        if not posts:
            self.stdout.write(self.style.WARNING(
                "No posts found. Run seed_cloud_data first."
            ))
            return

        users_created = 0
        apps_created = 0
        consents_created = 0

        for index, (email, full_name, phone) in enumerate(PORTAL_USERS):
            user, user_created = CandidatePortalUser.objects.get_or_create(
                email=email,
                defaults={
                    "full_name": full_name,
                    "phone": phone,
                    "otp_verified": True,
                    "is_active": True,
                },
            )
            if user_created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
                users_created += 1
            else:
                changed = []
                if not user.full_name:
                    user.full_name = full_name
                    changed.append("full_name")
                if not user.phone:
                    user.phone = phone
                    changed.append("phone")
                if not user.otp_verified:
                    user.otp_verified = True
                    changed.append("otp_verified")
                if changed:
                    user.save(update_fields=changed)

            first_name, _, last_name = full_name.partition(" ")
            candidate = Candidate.objects.filter(portal_user=user).first()
            if candidate is None:
                candidate = Candidate.objects.filter(email=email).first()
                if candidate is not None:
                    candidate.portal_user = user
                    candidate.save(update_fields=["portal_user"])
                else:
                    candidate = Candidate.objects.create(
                        portal_user=user,
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        mobile=phone,
                        date_of_birth=date(1991 + index, (index % 12) + 1, 10 + index),
                    )

            # Three applications per candidate, spread across the demo posts.
            for offset in range(3):
                post = posts[(index + offset) % len(posts)]
                _, app_created = Application.objects.get_or_create(
                    post=post,
                    candidate=candidate,
                    defaults={
                        "application_id": f"DEMO-{index + 1}-{post.pk}",
                        "status": STATUSES[(index + offset) % len(STATUSES)],
                        "resume_score": 62 + index * 5 + offset,
                    },
                )
                if app_created:
                    apps_created += 1

            _, consent_created = Consent.objects.get_or_create(
                candidate_portal_user=user,
                purpose="application",
                defaults={
                    "scope_text": (
                        "Demo consent for application processing under the "
                        "Digital Personal Data Protection Act, 2023."
                    ),
                    "expires_at": timezone.now() + timedelta(days=365),
                    "ip_address": "127.0.0.1",
                },
            )
            if consent_created:
                consents_created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Portal demo ready: {len(PORTAL_USERS)} users "
            f"({users_created} new), {apps_created} applications, "
            f"{consents_created} consents."
        ))
