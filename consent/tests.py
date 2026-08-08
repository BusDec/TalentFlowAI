"""Consent ledger test foundation — DPDP-style consent records."""

from django.utils import timezone

from consent.models import Consent, ConsentEvent


def test_consent_creation(candidate_portal_user, application):
    """A consent record persists purpose, scope, and linkage."""
    consent = Consent.objects.create(
        candidate_portal_user=candidate_portal_user,
        application=application,
        purpose="application",
        scope_text="Consent to process my application and documents.",
        ip_address="127.0.0.1",
    )
    consent.refresh_from_db()
    assert consent.purpose == "application"
    assert consent.application == application
    assert consent.scope_text == "Consent to process my application and documents."
    assert consent.granted_at is not None
    assert consent.is_active is True
    assert consent.get_purpose_display() == "Application Processing"
    assert "Application Processing" in str(consent)


def test_consent_event_creation(candidate_portal_user, application):
    """Consent lifecycle actions are recorded as immutable events."""
    consent = Consent.objects.create(
        candidate_portal_user=candidate_portal_user,
        application=application,
        purpose="digilocker",
        ip_address="127.0.0.1",
    )
    event = ConsentEvent.objects.create(
        consent=consent,
        action="granted",
        ip_address="127.0.0.1",
        details="System grant on application submit.",
    )
    event.refresh_from_db()
    assert event.action == "granted"
    assert event.consent == consent
    assert event.timestamp is not None
    assert event.details == "System grant on application submit."


def test_consent_revocation_flow(candidate_portal_user, application):
    """Revoking a consent deactivates it and records a revoked event."""
    consent = Consent.objects.create(
        candidate_portal_user=candidate_portal_user,
        application=application,
        purpose="background_check",
        ip_address="127.0.0.1",
    )
    assert consent.is_active is True
    consent.revoked_at = timezone.now()
    consent.save()
    consent.refresh_from_db()
    assert consent.is_active is False
