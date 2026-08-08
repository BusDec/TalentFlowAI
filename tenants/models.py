"""Tenant (organisation) models — live in the public schema."""

from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class Client(TenantMixin):
    """An organisation served by TalentFlow AI (e.g. NEEPCO, NTPC)."""

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    created_on = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    auto_create_schema = True

    class Meta:
        verbose_name = "Tenant / Organisation"

    def __str__(self):
        return self.name


class Domain(DomainMixin):
    pass
