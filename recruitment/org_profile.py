"""Access helpers for the per-tenant OrgProfile singleton."""

from django.db import connection

from tenants.models import Client


def get_org_profile():
    """Return the current tenant's OrgProfile, creating it on first access.

    Never raises: name_en defaults to the tenant's Client.name (readable from
    tenant context because 'public' is in the search_path), falling back to
    the schema name. This helper is the tenant-onboarding skeleton — a new
    schema gets its profile on first access.
    """
    from .models import OrgProfile

    try:
        name = Client.objects.get(schema_name=connection.schema_name).name
    except Client.DoesNotExist:
        name = connection.schema_name

    profile, _ = OrgProfile.objects.get_or_create(
        defaults={
            "name_en": name or connection.schema_name or "Organisation",
            "name_hi": "",
            "tagline_en": "",
            "tagline_hi": "",
            "address": "",
            "footer_motto": "",
            "contact_email": "",
            "website": "",
            "sbi_epay_text": "",
        }
    )
    return profile
