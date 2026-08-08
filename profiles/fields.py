"""Custom model fields for candidate profile data.

EncryptedTextField provides Fernet encryption at rest for sensitive PII such
as the Aadhaar number, so plaintext never lands in the tenant schema.
"""

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet():
    return Fernet(settings.ENCRYPTION_KEY.encode())


class EncryptedTextField(models.TextField):
    """TextField that encrypts (Fernet) at rest via get_prep_value/from_db_value."""

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        try:
            return _fernet().decrypt(value.encode()).decode()
        except (InvalidToken, ValueError):
            return value  # unreadable legacy value — surface as-is, never crash reads

    def get_prep_value(self, value):
        if value in (None, ""):
            return value
        return _fernet().encrypt(str(value).encode()).decode()
