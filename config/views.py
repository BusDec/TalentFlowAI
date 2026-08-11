"""Public landing page for TalentFlow — shows tenants, open vacancies, results."""

from django.shortcuts import render
from django_tenants.utils import get_public_schema_name, schema_context

from tenants.models import Client


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
                        from tenants.models import Domain

                        domain = Domain.objects.filter(tenant=client, is_primary=True).first()
                        tenant_data["portal_domain"] = (
                            domain.domain if domain else f"{client.schema_name}.localhost"
                        )
                except Exception:
                    pass
                tenants.append(tenant_data)
    except Exception:
        pass

    return render(request, "landing.html", {"tenants": tenants})
