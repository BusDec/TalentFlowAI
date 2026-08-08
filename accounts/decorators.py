"""Role-based access control decorators for internal staff views."""

from functools import wraps

from django.core.exceptions import PermissionDenied

from .models import UserTenantMembership


def check_role(request, *roles):
    """Return the active membership if the user holds one of ``roles``.

    Raises PermissionDenied for anonymous requests and for authenticated users
    who hold none of the required roles via an active ``UserTenantMembership``
    in the current tenant. Django superusers and memberships with the
    ``super_admin`` role bypass every gate (returning ``None``).
    """
    user = request.user
    if not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    if user.is_superuser:
        return None

    membership = UserTenantMembership.objects.filter(
        user=user,
        tenant=request.tenant,
        is_active=True,
    ).first()
    if membership and membership.role == "super_admin":
        return None
    if membership and membership.role in roles:
        return membership

    raise PermissionDenied(f"Requires one of: {', '.join(roles)}")


def require_role(*roles):
    """View decorator: deny access unless the user holds one of ``roles``."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            check_role(request, *roles)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
