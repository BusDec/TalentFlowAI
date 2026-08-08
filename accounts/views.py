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


def access_denied(request):
    return render(request, "accounts/access_denied.html", status=403)
