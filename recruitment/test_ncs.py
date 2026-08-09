"""NCS / Employment Exchange feed adapter tests (Phase 4, Task 15)."""

import pytest
from django.test import override_settings

from recruitment.ncs_adapter import (
    NCSSubmissionReceipt,
    NCSVacancyPayload,
    NotConfigured,
    build_payload,
    publish_advertisement,
    publish_vacancy,
)


# ── build_payload (pure function, no DB needed) ─────────────────────────────


def test_build_payload_extracts_post_fields(tenant, advertisement):
    """build_payload maps Post fields into a NCSVacancyPayload."""
    post = advertisement.posts.first()
    payload = build_payload(post, org_name="NEEPCO", advt_number="N/01/2026")
    assert isinstance(payload, NCSVacancyPayload)
    assert payload.post_code == post.post_code
    assert payload.post_name == post.name
    assert payload.organisation == "NEEPCO"
    assert payload.vacancies == post.vacancies
    assert payload.qualification == post.qualification
    assert payload.advt_number == "N/01/2026"


def test_build_payload_uses_advt_defaults(tenant, advertisement):
    """When org_name / advt_number are not given, falls back to Advertisement."""
    post = advertisement.posts.first()
    payload = build_payload(post)
    assert payload.organisation == advertisement.title
    assert payload.advt_number == advertisement.advt_number


def test_build_payload_closing_date_iso(tenant, advertisement):
    """Closing date is in ISO (YYYY-MM-DD) format."""
    post = advertisement.posts.first()
    payload = build_payload(post)
    assert payload.closing_date == str(advertisement.closing_date)


# ── Mock mode (default) ────────────────────────────────────────────────────


def test_publish_vacancy_mock_returns_receipt(tenant, advertisement):
    """In mock mode, publish_vacancy returns a valid receipt."""
    post = advertisement.posts.first()
    receipt = publish_vacancy(post)
    assert isinstance(receipt, NCSSubmissionReceipt)
    assert receipt.ncs_ref.startswith("NCS-MOCK-")
    assert receipt.vacancies_published == post.vacancies
    assert receipt.status == "submitted"


def test_publish_vacancy_mock_unique_refs(tenant, advertisement):
    """Each mock submission gets a unique NCS reference."""
    post = advertisement.posts.first()
    refs = {publish_vacancy(post).ncs_ref for _ in range(5)}
    assert len(refs) == 5


def test_publish_advertisement_mock_returns_list(tenant, advertisement):
    """publish_advertisement returns one receipt per post."""
    posts = list(advertisement.posts.all())
    receipts = publish_advertisement(posts)
    assert len(receipts) == len(posts)
    for r in receipts:
        assert isinstance(r, NCSSubmissionReceipt)


def test_publish_advertisement_mock_empty_posts(tenant):
    """Empty post list returns empty receipts."""
    receipts = publish_advertisement([])
    assert receipts == []


# ── Real mode raises NotConfigured ─────────────────────────────────────────


@override_settings(NCS_MOCK=False)
def test_publish_vacancy_real_raises_not_configured(tenant, advertisement):
    """With mock disabled and no API keys, NotConfigured is raised."""
    post = advertisement.posts.first()
    with pytest.raises(NotConfigured, match="NCS employer API credentials"):
        publish_vacancy(post)


@override_settings(NCS_MOCK=False)
def test_publish_advertisement_real_raises_not_configured(tenant, advertisement):
    """publish_advertisement also raises NotConfigured in real mode."""
    posts = list(advertisement.posts.all())
    with pytest.raises(NotConfigured, match="NCS employer API credentials"):
        publish_advertisement(posts)
