"""Candidate-facing portal user — per-tenant auth for external candidates."""

from django.contrib.auth.models import AbstractBaseUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class CandidatePortalUser(AbstractBaseUser):
    """Authenticated candidate (distinct from internal HR User)."""

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, blank=True)
    full_name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    otp_verified = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = models.Manager()

    class Meta:
        verbose_name = "Candidate Portal User"

    def __str__(self):
        return self.full_name or self.email

    @property
    def is_staff(self):
        return False

    def has_perm(self, perm, obj=None):
        return False

    def has_module_perms(self, app_label):
        return False
