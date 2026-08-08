"""Tenant access control middleware.

Ensures a logged-in internal staff user (accounts.User) has an active
membership in the current tenant. Candidate portal users are exempt — they are
already scoped to the tenant by the portal auth backend.
"""

from django.shortcuts import redirect
from django.urls import Resolver404, resolve
from django.utils.deprecation import MiddlewareMixin
from django_tenants.utils import get_public_schema_name

from .models import User, UserTenantMembership


class TenantAccessMiddleware(MiddlewareMixin):
    def process_request(self, request):
        user = request.user

        if not user.is_authenticated:
            return None

        # Candidate portal users have no tenant-membership concept — skip.
        if not isinstance(user, User):
            return None

        # Never redirect the access-denied page to itself (redirect loop), and
        # always let auth endpoints through: a user whose tenant membership is
        # missing/inactive must still be able to log out (or log in), otherwise
        # every request — including POST /logout/ — bounces to access-denied
        # and the session never ends.
        try:
            match = resolve(request.path_info)
        except Resolver404:
            match = None
        if match and match.url_name in ("login", "logout", "access_denied"):
            return None

        if user.is_superuser:
            return None

        if request.tenant.schema_name == get_public_schema_name():
            return None

        has_access = UserTenantMembership.objects.filter(
            user=user,
            tenant=request.tenant,
            is_active=True,
        ).exists()

        if not has_access:
            return redirect("access_denied")

        return None
