"""NCS (National Career Service) / Employment Exchange feed adapter.

Publishes vacancies to the NCS portal so they reach employment exchanges
across India.  During development the adapter returns a synthetic submission
receipt; the real implementation requires NCS employer API credentials
(NCS_API_BASE, NCS_API_KEY) and raises ``NotConfigured`` when they are
absent.

Switch with ``NCS_MOCK=True/False`` in .env (default: True).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from recruitment.models import Post


# ── Exceptions ──────────────────────────────────────────────────────────────


class NCSError(RuntimeError):
    """Base error for NCS operations."""


class NotConfigured(NCSError):
    """Raised when real NCS credentials are missing and mock mode is off."""


# ── Result types ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NCSVacancyPayload:
    """Normalised payload sent (or simulated) to the NCS API."""

    post_code: str
    post_name: str
    organisation: str
    vacancies: int
    qualification: str
    experience: str
    pay_scale: str
    location: str
    age_limit: int | None
    closing_date: str  # ISO format
    advt_number: str


@dataclass(frozen=True)
class NCSSubmissionReceipt:
    """Acknowledgement returned after a successful vacancy submission."""

    ncs_ref: str
    submitted_at: date
    vacancies_published: int
    status: str = "submitted"


# ── Mock data ───────────────────────────────────────────────────────────────


def _mock_ncs_ref() -> str:
    return f"NCS-MOCK-{uuid.uuid4().hex[:8].upper()}"


# ── Public API ──────────────────────────────────────────────────────────────


def _is_mock() -> bool:
    return getattr(settings, "NCS_MOCK", True)


def build_payload(post: "Post", org_name: str = "", advt_number: str = "") -> NCSVacancyPayload:
    """Build a normalised vacancy payload from a *Post* instance.

    Pure function — no network calls.  Useful for testing and for the real
    adapter which will serialise the payload to JSON.
    """
    ad = post.advertisement
    return NCSVacancyPayload(
        post_code=post.post_code,
        post_name=post.name,
        organisation=org_name or getattr(ad, "title", ""),
        vacancies=post.vacancies,
        qualification=post.qualification,
        experience=post.experience_required or "Not specified",
        pay_scale=post.pay_scale or "As per rules",
        location=post.location or "Not specified",
        age_limit=post.max_age,
        closing_date=str(ad.closing_date) if ad.closing_date else "",
        advt_number=advt_number or ad.advt_number,
    )


def publish_vacancy(post: "Post", org_name: str = "", advt_number: str = "") -> NCSSubmissionReceipt:
    """Submit a single vacancy post to the NCS portal.

    Returns an :class:`NCSSubmissionReceipt` with a reference number.
    In mock mode the reference is synthetic; the real implementation POSTs to
    the NCS employer API and raises :class:`NotConfigured` when credentials
    are absent.
    """
    payload = build_payload(post, org_name=org_name, advt_number=advt_number)

    if _is_mock():
        return NCSSubmissionReceipt(
            ncs_ref=_mock_ncs_ref(),
            submitted_at=date.today(),
            vacancies_published=payload.vacancies,
        )

    # Real implementation would:
    #   1. authenticate with NCS_API_KEY against NCS_API_BASE
    #   2. POST the serialised payload
    #   3. parse the response into NCSSubmissionReceipt
    raise NotConfigured(
        "NCS employer API credentials are not configured. "
        "Set NCS_API_BASE and NCS_API_KEY in your environment, "
        "or keep NCS_MOCK=True for development."
    )


def publish_advertisement(posts: list["Post"], org_name: str = "", advt_number: str = "") -> list[NCSSubmissionReceipt]:
    """Publish all *posts* from an advertisement to NCS.

    Returns one receipt per post.  In mock mode every submission succeeds.
    The real implementation may batch or serialize depending on the API.
    """
    if _is_mock():
        return [publish_vacancy(p, org_name=org_name, advt_number=advt_number) for p in posts]

    # Real: batch or iterate with error handling per post.
    raise NotConfigured(
        "NCS employer API credentials are not configured. "
        "Set NCS_API_BASE and NCS_API_KEY in your environment, "
        "or keep NCS_MOCK=True for development."
    )
