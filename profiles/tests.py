"""Tests for PII encryption at rest (Phase 1.2).

CandidateProfile.aadhar_no is stored Fernet-encrypted in the tenant schema;
these tests verify round-tripping, ciphertext-at-rest, masking, and that the
plaintext never leaks through the model's string representation.
"""

import pytest
from django.db import connection

from recruitment.models import Candidate

from .models import CandidateProfile


@pytest.fixture
def profile(db, tenant):
    """A CandidateProfile with a known Aadhaar number, saved to the tenant schema."""
    candidate = Candidate.objects.create(
        first_name="Priya",
        last_name="Sharma",
        email="priya@example.com",
        mobile="9876543210",
    )
    p = CandidateProfile.objects.create(candidate=candidate, aadhar_no="123456789012")
    return p


def test_roundtrip(profile):
    fresh = CandidateProfile.objects.get(pk=profile.pk)
    assert fresh.aadhar_no == "123456789012"


def test_at_rest_is_ciphertext(profile):
    with connection.cursor() as cursor:
        cursor.execute("SELECT aadhar_no FROM profiles_candidateprofile WHERE id = %s", [profile.pk])
        stored = cursor.fetchone()[0]
    assert stored is not None
    assert stored.startswith("gAAAA")
    assert stored != "123456789012"


def test_blank_stored_as_blank(db, tenant):
    candidate = Candidate.objects.create(
        first_name="Rohit",
        last_name="Kumar",
        email="rohit@example.com",
    )
    p = CandidateProfile.objects.create(candidate=candidate, aadhar_no="")
    with connection.cursor() as cursor:
        cursor.execute("SELECT aadhar_no FROM profiles_candidateprofile WHERE id = %s", [p.pk])
        stored = cursor.fetchone()[0]
    assert stored in ("", None)
    assert CandidateProfile.objects.get(pk=p.pk).aadhar_no == ""


def test_display_aadhaar_masks(profile):
    assert profile.display_aadhaar == "XXXX-XXXX-9012"


def test_display_aadhaar_not_provided_when_blank(db, tenant):
    candidate = Candidate.objects.create(
        first_name="Anita",
        last_name="Das",
        email="anita@example.com",
    )
    p = CandidateProfile.objects.create(candidate=candidate, aadhar_no="")
    assert p.display_aadhaar == "Not provided"


def test_plaintext_not_in_str(profile):
    assert "123456789012" not in str(profile)


def test_retention_date_field_exists(profile):
    assert profile.aadhar_retention_date is None
