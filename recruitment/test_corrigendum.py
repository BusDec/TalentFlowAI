"""Tests for Corrigendum model + views + notification wiring."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client

from conftest import TENANT_DOMAIN
from recruitment.models import Corrigendum


User = get_user_model()


def _make_user(username="hr_user"):
    return User.objects.create_user(
        username=username,
        password="pass",
        email=f"{username}@neepco.local",
    )


# ── Model tests ──────────────────────────────────────────────────────────────


def test_corrigendum_create(tenant, advertisement):
    """Corrigendum can be created with all required fields."""
    c = Corrigendum.objects.create(
        advertisement=advertisement,
        version=1,
        changes_text="Extended closing date to 15-Jan-2027.",
        published_date="2026-09-01",
    )
    assert c.pk is not None
    assert c.advertisement == advertisement
    assert c.version == 1
    assert c.changes_text == "Extended closing date to 15-Jan-2027."
    assert str(c.published_date) == "2026-09-01"
    assert c.is_active is True  # default
    assert c.created_at is not None


def test_corrigendum_str(tenant, advertisement):
    """__str__ includes advt number and version."""
    c = Corrigendum.objects.create(
        advertisement=advertisement,
        version=1,
        changes_text="Closing date extended.",
        published_date="2026-09-01",
    )
    s = str(c)
    assert advertisement.advt_number in s
    assert "v1" in s or "1" in s


def test_corrigendum_unique_version_per_advt(tenant, advertisement):
    """Unique constraint on (advertisement, version) prevents duplicates."""
    Corrigendum.objects.create(
        advertisement=advertisement,
        version=1,
        changes_text="First correction.",
        published_date="2026-09-01",
    )
    import pytest
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        Corrigendum.objects.create(
            advertisement=advertisement,
            version=1,
            changes_text="Duplicate version.",
            published_date="2026-09-02",
        )


def test_corrigendum_auto_version(tenant, advertisement):
    """Version increments correctly across multiple corrigenda."""
    c1 = Corrigendum.objects.create(
        advertisement=advertisement,
        version=1,
        changes_text="First.",
        published_date="2026-09-01",
    )
    c2 = Corrigendum.objects.create(
        advertisement=advertisement,
        version=2,
        changes_text="Second.",
        published_date="2026-10-01",
    )
    assert c1.version == 1
    assert c2.version == 2


def test_corrigendum_reverse_relation(tenant, advertisement):
    """advertisement.corrigenda reverse relation works."""
    Corrigendum.objects.create(
        advertisement=advertisement,
        version=1,
        changes_text="First.",
        published_date="2026-09-01",
    )
    Corrigendum.objects.create(
        advertisement=advertisement,
        version=2,
        changes_text="Second.",
        published_date="2026-10-01",
    )
    assert advertisement.corrigenda.count() == 2


# ── View tests ───────────────────────────────────────────────────────────────


def test_corrigendum_create_view(tenant, advertisement, staff_user):
    """hr_manager can POST to create a corrigendum; redirects on success."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)

    resp = client.post(
        f"/advertisements/{advertisement.id}/corrigendum/",
        {"changes_text": "Extended deadline by 15 days."},
    )
    # View redirects back to detail page on success.
    assert resp.status_code == 302
    assert Corrigendum.objects.filter(advertisement=advertisement).count() == 1
    c = Corrigendum.objects.first()
    assert c.version == 1
    assert c.changes_text == "Extended deadline by 15 days."


def test_corrigendum_auto_bumps_version(tenant, advertisement, staff_user):
    """Second corrigendum creation auto-assigns version=2."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)

    client.post(
        f"/advertisements/{advertisement.id}/corrigendum/",
        {"changes_text": "First."},
    )
    client.post(
        f"/advertisements/{advertisement.id}/corrigendum/",
        {"changes_text": "Second."},
    )
    assert Corrigendum.objects.filter(advertisement=advertisement).count() == 2
    versions = list(
        Corrigendum.objects.filter(advertisement=advertisement)
        .order_by("version")
        .values_list("version", flat=True)
    )
    assert versions == [1, 2]


def test_corrigendum_viewer_cannot_create(tenant, advertisement, viewer_user):
    """Non-hr_manager roles cannot create corrigenda."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(viewer_user)

    resp = client.post(
        f"/advertisements/{advertisement.id}/corrigendum/",
        {"changes_text": "Should not be created."},
    )
    # Viewer role is forbidden.
    assert resp.status_code == 403
    assert Corrigendum.objects.count() == 0


def test_corrigendum_empty_text_rejected(tenant, advertisement, staff_user):
    """Empty changes_text is rejected with an error redirect."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)

    resp = client.post(
        f"/advertisements/{advertisement.id}/corrigendum/",
        {"changes_text": ""},
    )
    # Redirect back with error message.
    assert resp.status_code == 302
    assert Corrigendum.objects.count() == 0


def test_corrigendum_shows_on_detail(tenant, advertisement, viewer_user):
    """Corrigendum appears on the advertisement detail page."""
    Corrigendum.objects.create(
        advertisement=advertisement,
        version=1,
        changes_text="Closing date extended to 31-Jan-2027.",
        published_date="2026-09-01",
    )
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(viewer_user)

    resp = client.get(f"/advertisements/{advertisement.id}/")
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Corrigend" in content
    assert "Closing date extended" in content


# ── Notification tests ───────────────────────────────────────────────────────


def test_corrigendum_notifies_applicants(tenant, advertisement, application, staff_user):
    """Creating a corrigendum sends notification via the notify helper."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)

    with patch("recruitment.views.send_notification") as mock_notify:
        mock_notify.return_value = (True, "sent")
        client.post(
            f"/advertisements/{advertisement.id}/corrigendum/",
            {"changes_text": "New eligibility criteria added."},
        )
        mock_notify.assert_called()
        call_kwargs = mock_notify.call_args[1]
        assert "Corrigendum" in call_kwargs["subject"]
        assert application.candidate.email in call_kwargs["to"]


def test_corrigendum_notification_body(tenant, advertisement, application, staff_user):
    """Notification body includes the changes text and advt number."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)

    with patch("recruitment.views.send_notification") as mock_notify:
        mock_notify.return_value = (True, "sent")
        client.post(
            f"/advertisements/{advertisement.id}/corrigendum/",
            {"changes_text": "Updated pay scale."},
        )
        call_kwargs = mock_notify.call_args[1]
        assert "Updated pay scale" in call_kwargs["body"]
        assert advertisement.advt_number in call_kwargs["body"]
