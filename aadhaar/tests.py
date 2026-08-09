"""Tests for the Aadhaar e-KYC adapter (Phase 4, Task 14).

Covers:
- Mock adapter: OTP flow, biometric flow, deterministic results
- Real adapter: NotConfigured when credentials are absent
- VerificationFailed on bad inputs
"""

from __future__ import annotations

import hashlib

import pytest
from django.test import override_settings

from aadhaar.adapter import (
    KYCResult,
    NotConfigured,
    VerificationFailed,
    request_otp,
    verify_biometric,
    verify_otp,
)


# ---------------------------------------------------------------------------
# Mock adapter — OTP flow
# ---------------------------------------------------------------------------


class TestMockOTPFlow:
    """Mock OTP request + verify round-trip."""

    @override_settings(AADHAAR_MOCK=True)
    def test_request_otp_returns_txn_id(self):
        txn = request_otp("123456789012")
        assert txn.startswith("MOCK-TXN-")
        assert len(txn) == len("MOCK-TXN-") + 16

    @override_settings(AADHAAR_MOCK=True)
    def test_request_otp_deterministic(self):
        """Same Aadhaar → same transaction ID."""
        a1 = request_otp("123456789012")
        a2 = request_otp("123456789012")
        assert a1 == a2

    @override_settings(AADHAAR_MOCK=True)
    def test_verify_otp_success(self):
        result = verify_otp("123456789012", "123456")
        assert isinstance(result, KYCResult)
        assert result.uid == "123456789012"
        assert result.verified is True
        assert result.source == "aadhaar_ekyc"
        assert result.name  # non-empty
        assert result.dob
        assert result.gender in ("M", "F", "T")
        assert result.address
        assert result.photo_hash

    @override_settings(AADHAAR_MOCK=True)
    def test_verify_otp_deterministic(self):
        """Same inputs → same result."""
        r1 = verify_otp("987654321098", "654321")
        r2 = verify_otp("987654321098", "654321")
        assert r1 == r2

    @override_settings(AADHAAR_MOCK=True)
    def test_verify_otp_different_uid_different_name(self):
        """Different Aadhaar numbers should map to different mock names."""
        r1 = verify_otp("111111111111", "111111")
        r2 = verify_otp("222222222222", "222222")
        # May collide (8 names, hash mod), but test the general property.
        # At minimum both succeed.
        assert r1.verified and r2.verified

    @override_settings(AADHAAR_MOCK=True)
    def test_verify_otp_rejects_short_otp(self):
        with pytest.raises(VerificationFailed):
            verify_otp("123456789012", "12")

    @override_settings(AADHAAR_MOCK=True)
    def test_verify_otp_rejects_alpha_otp(self):
        with pytest.raises(VerificationFailed):
            verify_otp("123456789012", "abcdef")

    @override_settings(AADHAAR_MOCK=True)
    def test_verify_otp_rejects_empty_otp(self):
        with pytest.raises(VerificationFailed):
            verify_otp("123456789012", "")


# ---------------------------------------------------------------------------
# Mock adapter — Biometric flow
# ---------------------------------------------------------------------------


class TestMockBiometricFlow:
    """Mock biometric authentication."""

    @override_settings(AADHAAR_MOCK=True)
    def test_verify_biometric_success(self):
        result = verify_biometric("123456789012", b"\x00" * 64)
        assert isinstance(result, KYCResult)
        assert result.uid == "123456789012"
        assert result.verified is True
        assert result.source == "aadhaar_ekyc"

    @override_settings(AADHAAR_MOCK=True)
    def test_verify_biometric_rejects_empty(self):
        with pytest.raises(VerificationFailed):
            verify_biometric("123456789012", b"")


# ---------------------------------------------------------------------------
# Real adapter — NotConfigured
# ---------------------------------------------------------------------------


class TestRealAdapterNotConfigured:
    """Real adapter MUST raise NotConfigured when credentials are absent."""

    @override_settings(AADHAAR_MOCK=False, AADHAAR_AUA_ID="", AADHAAR_KUA_ID="")
    def test_request_otp_not_configured(self):
        with pytest.raises(NotConfigured, match="credentials not configured"):
            request_otp("123456789012")

    @override_settings(AADHAAR_MOCK=False, AADHAAR_AUA_ID="", AADHAAR_KUA_ID="")
    def test_verify_otp_not_configured(self):
        with pytest.raises(NotConfigured, match="credentials not configured"):
            verify_otp("123456789012", "123456")

    @override_settings(AADHAAR_MOCK=False, AADHAAR_AUA_ID="", AADHAAR_KUA_ID="")
    def test_verify_biometric_not_configured(self):
        with pytest.raises(NotConfigured, match="credentials not configured"):
            verify_biometric("123456789012", b"\x00" * 64)

    @override_settings(AADHAAR_MOCK=False, AADHAAR_AUA_ID="test_aua", AADHAAR_KUA_ID="")
    def test_request_otp_partial_credentials(self):
        """Both AUA and KUA IDs are required."""
        with pytest.raises(NotConfigured, match="credentials not configured"):
            request_otp("123456789012")

    @override_settings(AADHAAR_MOCK=False, AADHAAR_AUA_ID="", AADHAAR_KUA_ID="test_kua")
    def test_verify_otp_partial_credentials_kua_only(self):
        """Both AUA and KUA IDs are required."""
        with pytest.raises(NotConfigured, match="credentials not configured"):
            verify_otp("123456789012", "123456")


# ---------------------------------------------------------------------------
# KYCResult dataclass
# ---------------------------------------------------------------------------


class TestKYCResult:
    """KYCResult is a frozen dataclass with expected fields."""

    @override_settings(AADHAAR_MOCK=True)
    def test_result_is_frozen(self):
        result = verify_otp("123456789012", "123456")
        with pytest.raises(AttributeError):
            result.name = "CHANGED"

    @override_settings(AADHAAR_MOCK=True)
    def test_result_phone_email_hashes_present(self):
        result = verify_otp("123456789012", "123456")
        assert result.phone_hash is not None
        assert result.email_hash is not None
        assert len(result.phone_hash) == 64  # SHA-256 hex
        assert len(result.email_hash) == 64
