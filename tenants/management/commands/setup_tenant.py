"""Create or verify the NEEPCO tenant, its Azure domain, and OrgProfile.

Idempotent — safe to run on every startup. Handles:
  - Creating the neepco tenant schema if it doesn't exist
  - Registering the Azure domain (from AZURE_DOMAIN env or default)
  - Registering localhost domain for local dev
  - Ensuring OrgProfile exists in the tenant schema
"""

import os

from django.core.management.base import BaseCommand
from django.db import connection

from tenants.models import Client, Domain


class Command(BaseCommand):
    help = "Create/verify NEEPCO tenant, domains, and OrgProfile."

    def handle(self, *args, **options):
        connection.set_schema_to_public()

        # ── Tenant ────────────────────────────────────────────────────────────
        tenant, created = Client.objects.get_or_create(
            schema_name="neepco",
            defaults={"name": "NEEPCO", "code": "neepco"},
        )
        if created:
            tenant.create_schema(check_if_exists=True)
            self.stdout.write(self.style.SUCCESS(f"  Created neepco tenant (id={tenant.pk})"))
        else:
            self.stdout.write(f"  Neepco tenant exists (id={tenant.pk})")

        # ── Azure domain ──────────────────────────────────────────────────────
        azure_domain = os.environ.get("AZURE_DOMAIN", "tf-neepco-prod.azurewebsites.net")
        dom, d_created = Domain.objects.get_or_create(
            domain=azure_domain,
            defaults={"tenant": tenant, "is_primary": True},
        )
        if d_created:
            self.stdout.write(self.style.SUCCESS(f"  Created domain: {azure_domain}"))
        else:
            # Ensure it points to the right tenant
            if dom.tenant_id != tenant.pk:
                dom.tenant = tenant
                dom.save(update_fields=["tenant"])
                self.stdout.write(self.style.WARNING(f"  Fixed domain {azure_domain} → neepco"))
            else:
                self.stdout.write(f"  Domain exists: {azure_domain}")

        # ── Localhost domain (for local dev) ──────────────────────────────────
        localhost_domain = "neepco.localhost"
        loc, loc_created = Domain.objects.get_or_create(
            domain=localhost_domain,
            defaults={"tenant": tenant, "is_primary": False},
        )
        if loc_created:
            self.stdout.write(self.style.SUCCESS(f"  Created domain: {localhost_domain}"))
        else:
            self.stdout.write(f"  Domain exists: {localhost_domain}")

        # ── OrgProfile in tenant schema ───────────────────────────────────────
        from django_tenants.utils import schema_context

        with schema_context("neepco"):
            from recruitment.models import OrgProfile

            profile, p_created = OrgProfile.objects.get_or_create(
                defaults={
                    "name_en": tenant.name,
                    "name_hi": "नीपको",
                    "tagline_en": "Powering the North East",
                    "tagline_hi": "पूर्वोत्तर को ऊर्जा देना",
                    "address": "Brookland Compound, New Delhi — 110003",
                    "contact_email": "recruitment@neepco.co.in",
                    "website": "https://www.neepco.co.in",
                    "accent_color": "#0b3d91",
                },
            )
            if p_created:
                self.stdout.write(self.style.SUCCESS("  Created OrgProfile for NEEPCO"))
            else:
                self.stdout.write("  OrgProfile exists for NEEPCO")

        self.stdout.write(self.style.SUCCESS("Tenant setup complete."))
