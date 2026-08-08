"""Account / auth views for internal users."""

from django import forms
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods


class StyledAuthenticationForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={"class": "tf-input"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "tf-input"}))


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True
    next_page = reverse_lazy("dashboard")
    authentication_form = StyledAuthenticationForm


@require_http_methods(["GET", "POST"])
def logout_view(request):
    """Robust logout — works for both GET and POST, never raises."""
    try:
        auth_logout(request)
    except Exception:
        request.session.flush()
    return redirect("login")


def access_denied(request, exception=None):
    """Friendly 403 page — used for PermissionDenied (role gates) and the
    access_denied route (TenantAccessMiddleware redirect)."""
    current_roles = []
    if request.user.is_authenticated and hasattr(request, "tenant"):
        current_roles = list(
            request.user.tenant_memberships.filter(
                tenant=request.tenant, is_active=True
            ).values_list("role", flat=True)
        )
    return render(
        request,
        "accounts/access_denied.html",
        {"exception": exception, "current_roles": current_roles},
        status=403,
    )
