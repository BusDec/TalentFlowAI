"""Create or verify the demo tenant, its domains, and OrgProfile.

Idempotent — safe to run on every deployment. Handles:
  - Creating the demo tenant schema if it doesn't exist
  - Registering PRIMARY_DOMAIN (e.g. the Vercel hostname) when provided
  - Registering neepco.localhost for local development
  - Ensuring OrgProfile exists in the tenant schema
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from tenants.models import Client, Domain


class Command(BaseCommand):
    help = "Create/verify the demo tenant, domains, and OrgProfile."

    def handle(self, *args, **options):
        schema_name = settings.DEMO_TENANT_SCHEMA
        connection.set_schema_to_public()

        # ── Tenant ────────────────────────────────────────────────────────────
        tenant, created = Client.objects.get_or_create(
            schema_name=schema_name,
            defaults={"name": "NEEPCO", "code": schema_name},
        )
        if created:
            tenant.create_schema(check_if_exists=True)
            self.stdout.write(self.style.SUCCESS(f"  Created {schema_name} tenant (id={tenant.pk})"))
        else:
            self.stdout.write(f"  Tenant exists: {schema_name} (id={tenant.pk})")

        # ── Primary production domain (Vercel) ────────────────────────────────
        primary_domain = os.environ.get("PRIMARY_DOMAIN", "").strip().lower()
        if not primary_domain:
            primary_domain = "neepco.localhost"

        Domain.objects.filter(tenant=tenant, is_primary=True).exclude(
            domain=primary_domain
        ).update(is_primary=False)
        dom, d_created = Domain.objects.update_or_create(
            domain=primary_domain,
            defaults={"tenant": tenant, "is_primary": True},
        )
        if d_created:
            self.stdout.write(self.style.SUCCESS(f"  Created primary domain: {primary_domain}"))
        else:
            self.stdout.write(f"  Primary domain: {primary_domain}")

        # ── Localhost domain (for local dev) ──────────────────────────────────
        localhost_domain = "neepco.localhost"
        if primary_domain != localhost_domain:
            loc, loc_created = Domain.objects.get_or_create(
                domain=localhost_domain,
                defaults={"tenant": tenant, "is_primary": False},
            )
            if loc_created:
                self.stdout.write(self.style.SUCCESS(f"  Created domain: {localhost_domain}"))
            elif loc.tenant_id != tenant.pk:
                loc.tenant = tenant
                loc.save(update_fields=["tenant"])
                self.stdout.write(self.style.WARNING(f"  Fixed domain {localhost_domain} → {schema_name}"))
            else:
                self.stdout.write(f"  Domain exists: {localhost_domain}")

        # ── OrgProfile in tenant schema ───────────────────────────────────────
        from django_tenants.utils import schema_context

        with schema_context(schema_name):
            from recruitment.models import OrgProfile

            profile_defaults = {
                "name_en": tenant.name,
                "name_hi": "नीपको",
                "tagline_en": "Powering the North East",
                "tagline_hi": "पूर्वोत्तर को ऊर्जा देना",
                "address": "Brookland Compound, New Delhi — 110003",
                "contact_email": "recruitment@neepco.co.in",
                "website": "https://www.neepco.co.in",
                "accent_color": "#0b3d91",
            }
            profile, p_created = OrgProfile.objects.get_or_create(
                defaults=profile_defaults,
            )
            if p_created:
                self.stdout.write(self.style.SUCCESS("  Created OrgProfile for NEEPCO"))
            elif profile.name_en in ("", schema_name) and not profile.contact_email:
                # Migration 0010 seeds a placeholder row from the schema name.
                for field, value in profile_defaults.items():
                    setattr(profile, field, value)
                profile.save()
                self.stdout.write(self.style.SUCCESS("  Filled placeholder OrgProfile for NEEPCO"))
            else:
                self.stdout.write("  OrgProfile exists for NEEPCO")

        self.stdout.write(self.style.SUCCESS("Tenant setup complete."))
