"""Aadhaar e-KYC adapter — UIDAI AUA/KUA integration stub.

During Phase 4 development we operate against a MOCK service so nothing
blocks development while UIDAI AUA/KUA registration is pending.  The real
implementation should expose the same public API signatures so call sites
never change.

Switch with: AADHAAR_MOCK=False in .env once real credentials exist.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Optional

from django.conf import settings


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AadhaarError(RuntimeError):
    """Base error for Aadhaar adapter failures."""


class NotConfigured(AadhaarError):
    """Raised when the real adapter is selected but credentials are missing."""


class VerificationFailed(AadhaarError):
    """Raised when the UIDAI response indicates verification failure."""


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KYCResult:
    """Normalised e-KYC response from either the mock or real API."""

    uid: str                     # 12-digit Aadhaar number
    name: str                    # Full name as per UIDAI records
    dob: str                     # Date of birth (YYYY-MM-DD)
    gender: str                  # "M" / "F" / "T"
    address: str                 # Full address string
    photo_hash: str              # SHA-256 of the photo (placeholder)
    phone_hash: Optional[str]    # SHA-256 of the linked mobile (masked)
    email_hash: Optional[str]    # SHA-256 of the linked email (masked)
    verified: bool               # True when UIDAI confirms authenticity
    source: str                  # "aadhaar_ekyc"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def verify_otp(aadhaar_number: str, otp: str) -> KYCResult:
    """Perform Aadhaar e-KYC by OTP authentication.

    Args:
        aadhaar_number: 12-digit Aadhaar number (digits only, no spaces).
        otp: One-time password sent to the Aadhaar-linked mobile.

    Returns:
        KYCResult with the verified demographic data.

    Raises:
        NotConfigured: when real adapter is selected but AUA/KUA credentials
            are absent.
        VerificationFailed: when OTP validation or UIDAI response fails.
    """
    if _use_mock():
        return _mock_verify_otp(aadhaar_number, otp)

    # Real implementation would:
    #   1. Call UIDAI Auth API (AUA endpoint) with e-KYC request XML
    #   2. Validate the OTP against the Skey-encrypted block
    #   3. Parse the e-KYC XML response (demographics + photo)
    #   4. Return a KYCResult
    _check_real_credentials()
    raise NotImplementedError(
        "Real Aadhaar e-KYC integration not yet implemented. "
        "UIDAI AUA/KUA registration pending."
    )


def request_otp(aadhaar_number: str) -> str:
    """Initiate OTP generation for the given Aadhaar number.

    Args:
        aadhaar_number: 12-digit Aadhaar number.

    Returns:
        A transaction reference ID for the subsequent verify_otp call.

    Raises:
        NotConfigured: when real adapter is selected but AUA/KUA credentials
            are absent.
    """
    if _use_mock():
        return _mock_request_otp(aadhaar_number)

    _check_real_credentials()
    raise NotImplementedError(
        "Real Aadhaar e-KYC integration not yet implemented. "
        "UIDAI AUA/KUA registration pending."
    )


def verify_biometric(aadhaar_number: str, biometric_data: bytes) -> KYCResult:
    """Perform Aadhaar e-KYC by biometric authentication.

    Args:
        aadhaar_number: 12-digit Aadhaar number.
        biometric_data: Encrypted biometric payload (fingerprint/iris).

    Returns:
        KYCResult with the verified demographic data.

    Raises:
        NotConfigured: when real adapter is selected but AUA/KUA credentials
            are absent.
        VerificationFailed: when biometric validation fails.
    """
    if _use_mock():
        return _mock_verify_biometric(aadhaar_number, biometric_data)

    _check_real_credentials()
    raise NotImplementedError(
        "Real Aadhaar biometric e-KYC not yet implemented. "
        "UIDAI AUA/KUA registration pending."
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _use_mock() -> bool:
    """True when running in mock mode (default for dev/test)."""
    return getattr(settings, "AADHAAR_MOCK", True)


def _check_real_credentials() -> None:
    """Raise NotConfigured when the required env vars are absent."""
    aua_id = getattr(settings, "AADHAAR_AUA_ID", "") or ""
    kua_id = getattr(settings, "AADHAAR_KUA_ID", "") or ""
    if not aua_id or not kua_id:
        raise NotConfigured(
            "Aadhaar e-KYC credentials not configured. "
            "Set AADHAAR_AUA_ID and AADHAAR_KUA_ID in your .env file. "
            "Keep AADHAAR_MOCK=True for development."
        )


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

# Stable deterministic mock data keyed by Aadhaar number hash.
_MOCK_NAMES = [
    "Priya Sharma",
    "Rahul Kumar",
    "Anita Devi",
    "Vikram Singh",
    "Deepa Patel",
    "Suresh Yadav",
    "Meena Gupta",
    "Arjun Reddy",
]
_MOCK_GENDERS = ["M", "F", "M", "M", "F", "M", "F", "M"]
_MOCK_ADDRESSES = [
    "12 MG Road, New Delhi, Delhi 110001",
    "45 Gandhi Nagar, Mumbai, Maharashtra 400001",
    "78 Nehru Street, Chennai, Tamil Nadu 600001",
    "23 Netaji Road, Kolkata, West Bengal 700001",
    "56 Rajiv Chowk, Bengaluru, Karnataka 560001",
    "89 Patel Nagar, Ahmedabad, Gujarat 380001",
    "34 Tagore Lane, Hyderabad, Telangana 500001",
    "67 Tilak Marg, Lucknow, Uttar Pradesh 226001",
]


def _pick_index(aadhaar_number: str) -> int:
    """Deterministic index selection from Aadhaar number hash."""
    h = int(hashlib.sha256(aadhaar_number.encode()).hexdigest(), 16)
    return h % len(_MOCK_NAMES)


def _mock_request_otp(aadhaar_number: str) -> str:
    """Return a deterministic mock transaction ID."""
    h = hashlib.sha256(f"otp:{aadhaar_number}".encode()).hexdigest()[:16]
    return f"MOCK-TXN-{h}"


def _mock_verify_otp(aadhaar_number: str, otp: str) -> KYCResult:
    """Return deterministic mock demographic data.

    In mock mode, any 6-digit OTP is accepted.  The mock data is keyed off
    the Aadhaar number so repeated calls for the same UID return consistent
    results.
    """
    # In mock mode, accept any 6-digit OTP; reject obviously wrong ones.
    if not otp or len(otp) != 6 or not otp.isdigit():
        raise VerificationFailed("Invalid OTP format. Expected 6 digits.")

    idx = _pick_index(aadhaar_number)
    return KYCResult(
        uid=aadhaar_number,
        name=_MOCK_NAMES[idx],
        dob="1990-01-15",
        gender=_MOCK_GENDERS[idx],
        address=_MOCK_ADDRESSES[idx],
        photo_hash=hashlib.sha256(f"photo:{aadhaar_number}".encode()).hexdigest(),
        phone_hash=hashlib.sha256(f"phone:{aadhaar_number}".encode()).hexdigest(),
        email_hash=hashlib.sha256(f"email:{aadhaar_number}".encode()).hexdigest(),
        verified=True,
        source="aadhaar_ekyc",
    )


def _mock_verify_biometric(aadhaar_number: str, biometric_data: bytes) -> KYCResult:
    """Return deterministic mock data for biometric auth.

    Accepts any non-empty biometric payload.
    """
    if not biometric_data:
        raise VerificationFailed("Empty biometric payload.")

    idx = _pick_index(aadhaar_number)
    return KYCResult(
        uid=aadhaar_number,
        name=_MOCK_NAMES[idx],
        dob="1990-01-15",
        gender=_MOCK_GENDERS[idx],
        address=_MOCK_ADDRESSES[idx],
        photo_hash=hashlib.sha256(f"photo:{aadhaar_number}".encode()).hexdigest(),
        phone_hash=hashlib.sha256(f"phone:{aadhaar_number}".encode()).hexdigest(),
        email_hash=hashlib.sha256(f"email:{aadhaar_number}".encode()).hexdigest(),
        verified=True,
        source="aadhaar_ekyc",
    )
