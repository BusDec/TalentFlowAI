"""Template context processors for the candidate portal."""

from django_tenants.utils import get_public_schema_name


def org_profile(request):
    """Return OrgProfile for the current tenant, or empty dict in public schema."""
    from django.db import connection

    if connection.schema_name == get_public_schema_name():
        return {"org_profile": type("Obj", (), {"name_en": "TalentFlow AI", "name_hi": "", "tagline_en": "", "logo": None, "accent_color": "#0b3d91"})()}

    try:
        from recruitment.org_profile import get_org_profile
        return {"org_profile": get_org_profile()}
    except Exception:
        return {"org_profile": type("Obj", (), {"name_en": "TalentFlow AI", "name_hi": "", "tagline_en": "", "logo": None, "accent_color": "#0b3d91"})()}
