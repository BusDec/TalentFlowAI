"""Public landing page for TalentFlow — shows tenants, open vacancies, results.

Also contains the tenant onboarding wizard (public, no auth required).
"""

import re

from django.contrib.auth import get_user_model
from django.contrib import messages
from django.db import connection
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django_tenants.utils import get_public_schema_name, schema_context

from tenants.models import Client, Domain


def landing_page(request):
    """Public landing page showing all tenants and their recruitment status."""
    tenants = []
    try:
        with schema_context(get_public_schema_name()):
            for client in Client.objects.filter(is_active=True).exclude(
                schema_name=get_public_schema_name()
            ):
                tenant_data = {
                    "name": client.name,
                    "code": client.code,
                    "schema": client.schema_name,
                    "advertisements": [],
                    "total_vacancies": 0,
                    "total_applications": 0,
                }
                try:
                    with schema_context(client.schema_name):
                        from recruitment.models import Advertisement, Application

                        # Get active advertisements
                        advts = Advertisement.objects.filter(is_active=True).order_by(
                            "-published_date"
                        )[:5]
                        for advt in advts:
                            advt_data = {
                                "number": advt.advt_number,
                                "title": advt.title,
                                "closing_date": advt.closing_date,
                                "posts": [],
                            }
                            total_vacancies = 0
                            for post in advt.posts.all():
                                advt_data["posts"].append(
                                    {
                                        "name": post.name,
                                        "code": post.post_code,
                                        "vacancies": post.vacancies,
                                    }
                                )
                                total_vacancies += post.vacancies
                            advt_data["total_vacancies"] = total_vacancies
                            tenant_data["advertisements"].append(advt_data)
                            tenant_data["total_vacancies"] += total_vacancies

                        # Get application counts
                        tenant_data["total_applications"] = Application.objects.count()
                        tenant_data["offered_count"] = Application.objects.filter(
                            status="offered"
                        ).count()
                        tenant_data["joined_count"] = Application.objects.filter(
                            status="joined"
                        ).count()

                        # Get domain for portal link
                        domain = Domain.objects.filter(tenant=client, is_primary=True).first()
                        if domain:
                            dom = domain.domain
                            # Production domains use HTTPS; localhost uses HTTP
                            if "localhost" in dom or "127.0.0.1" in dom:
                                tenant_data["portal_domain"] = dom
                                tenant_data["portal_url"] = f"http://{dom}:8000"
                            else:
                                tenant_data["portal_domain"] = dom
                                tenant_data["portal_url"] = f"https://{dom}"
                        else:
                            tenant_data["portal_domain"] = f"{client.schema_name}.localhost:8000"
                            tenant_data["portal_url"] = f"http://{client.schema_name}.localhost:8000"
                except Exception:
                    pass
                tenants.append(tenant_data)
    except Exception:
        pass

    return render(request, "landing.html", {"tenants": tenants})


# ── Tenant Onboarding Wizard ──────────────────────────────────────────────────

_WIZARD_STEPS = ["Organization", "Admin Account", "Branding", "Review & Create"]


def _validate_schema_name(name):
    """Schema names must be lowercase alphanumeric + underscores, 3-50 chars."""
    return bool(re.match(r"^[a-z][a-z0-9_]{2,49}$", name))


def onboarding(request):
    """Multi-step tenant onboarding wizard.

    GET: render the wizard form (step via ?step=N query param).
    POST: create the tenant, domain, admin user, and OrgProfile.
    """
    step = int(request.GET.get("step", 1))
    errors = []
    form_data = {}

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "create":
            # ── Validate all fields ───────────────────────────────────────
            org_name = request.POST.get("org_name", "").strip()
            schema_name = request.POST.get("schema_name", "").strip().lower()
            domain_name = request.POST.get("domain_name", "").strip().lower()
            admin_username = request.POST.get("admin_username", "").strip()
            admin_email = request.POST.get("admin_email", "").strip()
            admin_password = request.POST.get("admin_password", "")
            accent_color = request.POST.get("accent_color", "#0b3d91").strip()
            tagline = request.POST.get("tagline", "").strip()

            form_data = {
                "org_name": org_name, "schema_name": schema_name,
                "domain_name": domain_name, "admin_username": admin_username,
                "admin_email": admin_email, "accent_color": accent_color,
                "tagline": tagline,
            }

            if not org_name:
                errors.append("Organization name is required.")
            if not _validate_schema_name(schema_name):
                errors.append("Schema name: lowercase letters/digits/underscores, 3-50 chars, start with letter.")
            if not domain_name:
                errors.append("Domain name is required.")
            if Client.objects.filter(schema_name=schema_name).exists():
                errors.append(f'Schema "{schema_name}" already exists.')
            if Domain.objects.filter(domain=domain_name).exists():
                errors.append(f'Domain "{domain_name}" is already registered.')
            if not admin_username or len(admin_username) < 3:
                errors.append("Admin username must be at least 3 characters.")
            if not admin_email or "@" not in admin_email:
                errors.append("A valid admin email is required.")
            if not admin_password or len(admin_password) < 8:
                errors.append("Admin password must be at least 8 characters.")

            if not errors:
                # ── Create tenant ─────────────────────────────────────────
                connection.set_schema_to_public()
                tenant = Client.objects.create(
                    name=org_name,
                    schema_name=schema_name,
                    code=schema_name,
                )
                tenant.create_schema(check_if_exists=True)

                # ── Register domain ───────────────────────────────────────
                Domain.objects.create(
                    domain=domain_name,
                    tenant=tenant,
                    is_primary=True,
                )

                # ── Create admin user + membership ────────────────────────
                User = get_user_model()
                admin_user, _ = User.objects.get_or_create(
                    username=admin_username,
                    defaults={
                        "email": admin_email,
                        "first_name": org_name.split()[0] if org_name else "",
                        "is_staff": True,
                        "is_superuser": True,
                        "is_active": True,
                    },
                )
                admin_user.set_password(admin_password)
                admin_user.save()

                from accounts.models import UserTenantMembership
                UserTenantMembership.objects.get_or_create(
                    user=admin_user,
                    tenant=tenant,
                    defaults={"role": "org_admin", "is_active": True},
                )

                # ── Run tenant migrations ─────────────────────────────────
                from django.core.management import call_command
                call_command("migrate_schemas", schema_name=schema_name, interactive=False)

                # ── Create OrgProfile ─────────────────────────────────────
                with schema_context(schema_name):
                    from recruitment.models import OrgProfile
                    OrgProfile.objects.get_or_create(
                        defaults={
                            "name_en": org_name,
                            "tagline_en": tagline,
                            "accent_color": accent_color,
                            "contact_email": admin_email,
                        },
                    )

                # ── Done — show success ───────────────────────────────────
                protocol = "https" if "localhost" not in domain_name else "http"
                port = ":8000" if "localhost" in domain_name else ""
                return render(request, "onboarding.html", {
                    "step": 5,
                    "steps": _WIZARD_STEPS,
                    "success": True,
                    "tenant": tenant,
                    "domain": domain_name,
                    "portal_url": f"{protocol}://{domain_name}{port}",
                })

            # Validation failed — re-render step 4 with errors
            step = 4

        else:
            # Navigation between steps
            step = int(action) if action.isdigit() else step
            form_data = {k: request.POST.get(k, "") for k in [
                "org_name", "schema_name", "domain_name",
                "admin_username", "admin_email", "admin_password",
                "accent_color", "tagline",
            ]}

    return render(request, "onboarding.html", {
        "step": step,
        "steps": _WIZARD_STEPS,
        "form_data": form_data,
        "errors": errors,
    })
