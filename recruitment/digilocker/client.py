"""DigiLocker integration layer.

During Phase I development we operate against a MOCK service so nothing blocks
development while DigiLocker organisation registration is pending. The real
implementation should expose the same `fetch_documents(consent_reference)` and
`verify_signature(document)` signatures, so call sites never change.

Switch with: DIGILOCKER_MOCK=False in .env once real credentials exist.
"""

import datetime
from django.conf import settings

from .mock import MOCK_DOCUMENTS


class DigiLockerError(RuntimeError):
    """Base exception for all DigiLocker integration errors."""


class NotConfigured(DigiLockerError):
    """Raised when real DigiLocker credentials are missing and mock mode is off."""


class DocumentResult:
    """Normalised document descriptor returned by either the mock or real API."""

    def __init__(self, doc_type, issuer, issue_date, data, signature_valid=True, source="digilocker"):
        self.doc_type = doc_type
        self.issuer = issuer
        self.issue_date = issue_date
        self.data = data  # dict of extracted fields
        self.signature_valid = signature_valid
        self.source = source


def _check_api_key():
    """Raise NotConfigured when real DigiLocker is selected but API key is absent."""
    if not getattr(settings, "DIGILOCKER_API_KEY", ""):
        raise NotConfigured(
            "DigiLocker requires a DIGILOCKER_API_KEY environment variable. "
            "Set it in your .env file, or keep DIGILOCKER_MOCK=True for development."
        )


def fetch_documents(consent_reference, candidate_email=None, dob=None):
    """Return a list of DocumentResult for the consented candidate.

    In mock mode this returns synthetic documents derived from the candidate's
    details so downstream verification logic can be exercised end-to-end.
    """
    if getattr(settings, "DIGILOCKER_MOCK", True):
        return _mock_fetch(consent_reference, candidate_email, dob)

    _check_api_key()
    # Real implementation would:
    #   1. exchange consent token for an access token
    #   2. call DigiLocker issuer search API
    #   3. fetch + verify documents
    #   4. return list[DocumentResult]
    raise DigiLockerError("Real DigiLocker integration not yet implemented.")


def verify_signature(document_result):
    """Return True when the digital signature verifies."""
    if getattr(settings, "DIGILOCKER_MOCK", True):
        return document_result.signature_valid

    _check_api_key()
    # Real implementation: verify XMLDSig against issuer cert.
    raise DigiLockerError("Real DigiLocker integration not yet implemented.")


def _mock_fetch(consent_reference, candidate_email=None, dob=None):
    dob_value = dob.isoformat() if isinstance(dob, (datetime.date, datetime.datetime)) else (dob or "1990-01-01")
    base = {
        "name": "SAMPLE CANDIDATE",
        "dob": dob_value,
        "father_name": "SAMPLE FATHER",
    }
    docs = []
    for spec in MOCK_DOCUMENTS:
        data = dict(base)
        data.update(spec.get("data", {}))
        docs.append(
            DocumentResult(
                doc_type=spec["doc_type"],
                issuer=spec["issuer"],
                issue_date=spec["issue_date"],
                data=data,
                signature_valid=spec.get("signature_valid", True),
            )
        )
    return docs
