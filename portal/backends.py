"""Authentication backend for candidate portal users.

CandidatePortalUser is a separate model from the internal accounts.User.
Django's default ModelBackend reloads the session user from AUTH_USER_MODEL
(accounts.User), so candidates need their own backend.
"""

from django.contrib.auth.backends import BaseBackend

from .models import CandidatePortalUser


class CandidatePortalBackend(BaseBackend):
    """Loads session users from the CandidatePortalUser model."""

    def authenticate(self, request, email=None, password=None, **kwargs):
        # Phase I uses OTP login; no direct password authentication.
        return None

    def get_user(self, user_id):
        try:
            return CandidatePortalUser.objects.get(pk=user_id)
        except (CandidatePortalUser.DoesNotExist, TypeError, ValueError):
            return None

    def user_can_authenticate(self, user):
        return user is not None and user.is_active
