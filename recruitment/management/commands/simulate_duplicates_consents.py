"""Simulate duplicate applications across advertisements + consent ledger entries.

Deterministic and idempotent so it can be re-run safely.
"""

import hashlib
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from consent.models import Consent
from portal.models import CandidatePortalUser
from recruitment.models import Application, Candidate, Post


class Command(BaseCommand):
    help = "Plant deliberate duplicate candidates and generate consent ledger entries"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting duplicate + consent simulation..."))

        posts = list(Post.objects.order_by("id"))
        if len(posts) < 2:
            self.stdout.write(self.style.WARNING(
                "Need at least 2 posts. Run simulate_neepco_advt first."
            ))
            return

        # --- Duplicate candidates across advertisements ---------------------
        dup_count = 0
        for i in range(5):
            # Deterministic choice so re-runs create the SAME candidates/apps.
            post_a = posts[i % len(posts)]
            post_b = posts[(i + 1) % len(posts)]

            first = ["Rahul", "Priya", "Amit", "Sneha", "Vikram"][i]
            last = ["Sharma", "Patel", "Verma", "Gupta", "Singh"][i]
            email = f"dup.{first.lower()}.{last.lower()}{i}@example.com"
            dob = date(1992, 5, 15)
            mobile = f"99{10000000 + i * 1000}"

            candidate, created = Candidate.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "mobile": mobile,
                    "date_of_birth": dob,
                },
            )

            for post in (post_a, post_b):
                # Deterministic application id for idempotency.
                digest = hashlib.md5(
                    f"{post.post_code}-{candidate.email}".encode()
                ).hexdigest()[:6].upper()
                app_id = f"DUP-{digest}"
                app, app_created = Application.objects.get_or_create(
                    post=post,
                    candidate=candidate,
                    defaults={"application_id": app_id, "status": "received"},
                )
                # Reuse the same application id if one was already created.
                if not app_created and app.application_id != app_id:
                    app.application_id = app_id
                    app.save(update_fields=["application_id"])

            # The post_save signal automatically flags the second application.
            if created:
                dup_count += 1

        # --- Consent ledger entries ------------------------------------------
        users = list(CandidatePortalUser.objects.all())
        if not users:
            self.stdout.write(self.style.WARNING(
                "No portal users. Consent entries skipped — create via the portal register flow."
            ))
        consent_count = 0
        for _ in range(10):
            user = users[random.randint(0, len(users) - 1)] if users else None
            if not user:
                break
            purpose = random.choice(
                ["application", "digilocker", "background_check", "resume_parsing"]
            )
            _, created = Consent.objects.get_or_create(
                candidate_portal_user=user,
                purpose=purpose,
                defaults={
                    "scope_text": f"Consent for {purpose} processing under DPDP.",
                    "expires_at": timezone.now() + timedelta(days=365),
                    "ip_address": f"192.168.1.{random.randint(2, 250)}",
                },
            )
            if created:
                consent_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Simulation complete. Duplicate candidates planted: {dup_count}, "
            f"consent records: {consent_count}."
        ))
