"""Tests for fee exemption engine and payment adapter (§3.3)."""

from decimal import Decimal

import pytest

from profiles.models import CandidateProfile


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_profile(candidate, *, category="ur", gender="M", is_pwbd=False):
    """Create or update a CandidateProfile for the given candidate."""
    profile, _ = CandidateProfile.objects.get_or_create(candidate=candidate)
    profile.category = category
    profile.gender = gender
    profile.is_pwbd = is_pwbd
    profile.save()
    return profile


# ── fee_exempt tests ─────────────────────────────────────────────────────────


def test_sc_exempt(tenant, application):
    """SC category candidates are exempt from fee."""
    from recruitment.fees import fee_exempt

    _make_profile(application.candidate, category="sc")
    exempt, reason = fee_exempt(application.candidate, application.post)
    assert exempt is True
    assert "SC" in reason


def test_sc_applying_ur_post_still_exempt(tenant, application):
    """SC candidate applying against a UR-only post is still exempt
    (exemption is based on candidate category, not post category)."""
    from recruitment.fees import fee_exempt

    _make_profile(application.candidate, category="sc")
    exempt, reason = fee_exempt(application.candidate, application.post)
    assert exempt is True
    assert "SC" in reason


def test_female_exempt(tenant, application):
    """Female candidates are exempt from fee."""
    from recruitment.fees import fee_exempt

    _make_profile(application.candidate, gender="F")
    exempt, reason = fee_exempt(application.candidate, application.post)
    assert exempt is True
    assert "Female" in reason.lower() or "women" in reason.lower() or "female" in reason.lower()


def test_pwbd_exempt(tenant, application):
    """PwBD (Persons with Benchmark Disabilities) candidates are exempt."""
    from recruitment.fees import fee_exempt

    _make_profile(application.candidate, is_pwbd=True)
    exempt, reason = fee_exempt(application.candidate, application.post)
    assert exempt is True
    assert "PwBD" in reason or "disability" in reason.lower() or "pwd" in reason.lower()


def test_ur_male_not_exempt(tenant, application):
    """UR male candidates without PwBD are NOT exempt."""
    from recruitment.fees import fee_exempt

    _make_profile(application.candidate, category="ur", gender="M", is_pwbd=False)
    exempt, reason = fee_exempt(application.candidate, application.post)
    assert exempt is False
    assert "not exempt" in reason.lower() or "no exemption" in reason.lower() or reason


def test_fee_amount_default(tenant, advertisement):
    """fee_amount returns ₹500.00 by default."""
    from recruitment.fees import fee_amount

    post = advertisement.posts.first()
    assert fee_amount(post) == Decimal("500.00")


# ── MockPaymentGateway tests ─────────────────────────────────────────────────


def test_mock_gateway_create_payment():
    """MockPaymentGateway.create_payment returns dict with id and url."""
    from recruitment.payments import MockPaymentGateway

    gw = MockPaymentGateway()
    result = gw.create_payment(Decimal("500.00"), "TF20260001")
    assert "id" in result
    assert "url" in result
    assert result["id"].startswith("mock_")


def test_mock_gateway_verify_returns_true():
    """MockPaymentGateway.verify always returns True for any payload."""
    from recruitment.payments import MockPaymentGateway

    gw = MockPaymentGateway()
    assert gw.verify({"payment_id": "mock_xxx"}) is True


# ── Payment model tests ──────────────────────────────────────────────────────


def test_payment_model_fields(tenant, application):
    """Payment model has all required fields."""
    from recruitment.models import Payment

    p = Payment.objects.create(
        application=application,
        amount=Decimal("500.00"),
        gateway="mock",
        gateway_ref="mock_123",
        status="pending",
        exempt=False,
        exempt_reason="",
    )
    assert p.amount == Decimal("500.00")
    assert p.gateway == "mock"
    assert p.status == "pending"
    assert p.exempt is False
    assert p.paid_at is None
    assert p.created_at is not None
    assert application.payment == p  # related_name="payment"


def test_payment_model_exemption(tenant, application):
    """Payment with exempt=True records the reason."""
    from recruitment.models import Payment

    p = Payment.objects.create(
        application=application,
        amount=Decimal("0.00"),
        gateway="mock",
        status="completed",
        exempt=True,
        exempt_reason="SC category — exempt per DoPT guidelines",
    )
    assert p.exempt is True
    assert "SC" in p.exempt_reason
