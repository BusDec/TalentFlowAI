"""Tenant (Client + Domain) model test foundation — public schema."""

from django_tenants.utils import schema_exists

from tenants.models import Client as TenantClient
from tenants.models import Domain


def test_tenant_schema_created(db):
    """A second organisation gets its own schema and primary domain."""
    tenant = TenantClient.objects.create(
        schema_name="acmecorp", name="Acme Power Corp", code="acme"
    )
    Domain.objects.create(domain="acme.localhost", tenant=tenant, is_primary=True)

    assert tenant.schema_name == "acmecorp"
    assert str(tenant) == "Acme Power Corp"
    assert schema_exists("acmecorp")
    assert Domain.objects.filter(tenant=tenant, is_primary=True).count() == 1
