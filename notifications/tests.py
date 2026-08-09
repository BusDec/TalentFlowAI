"""Tests for notifications app — outbox, console provider, acknowledgement wiring."""

import pytest
from django.urls import reverse

from notifications import notify
from notifications.models import NotificationOutbox, NotificationTemplate
from recruitment.models import Application


# ── notify() + outbox tests ─────────────────────────────────────────────────


def test_notify_creates_outbox_row(tenant):
    """notify() creates an outbox row with status 'sent' for console provider."""
    ok, detail = notify("sms", "9876543210", "Test Subject", "Test body")
    assert ok is True
    assert detail == "sent"

    row = NotificationOutbox.objects.latest("created_at")
    assert row.channel == "sms"
    assert row.to == "9876543210"
    assert row.subject == "Test Subject"
    assert row.body == "Test body"
    assert row.status == "sent"
    assert row.error == ""


def test_notify_records_failed_status(tenant, monkeypatch):
    """When the provider fails, outbox status is 'failed' with error detail."""
    from notifications import providers

    def _fail(self, channel, to, subject, body):
        return False, "gateway timeout"

    monkeypatch.setattr(providers, "get_provider", lambda: type("P", (), {"send": _fail})())

    ok, detail = notify("sms", "9876543210", "sub", "body")
    assert ok is False
    assert detail == "gateway timeout"

    row = NotificationOutbox.objects.latest("created_at")
    assert row.status == "failed"
    assert "gateway timeout" in row.error


def test_notify_never_raises(tenant, monkeypatch):
    """notify() catches provider exceptions and records them as failures."""
    from notifications import providers

    def _boom(self, channel, to, subject, body):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(providers, "get_provider", lambda: type("P", (), {"send": _boom})())

    ok, detail = notify("sms", "9876543210", "sub", "body")
    assert ok is False
    assert "kaboom" in detail

    row = NotificationOutbox.objects.latest("created_at")
    assert row.status == "failed"
    assert "kaboom" in row.error


def test_notify_email_channel(tenant):
    """notify() works with email channel."""
    ok, _ = notify("email", "user@example.com", "Welcome", "Hello!")
    assert ok is True
    row = NotificationOutbox.objects.latest("created_at")
    assert row.channel == "email"
    assert row.to == "user@example.com"


def test_notify_portal_channel(tenant):
    """notify() works with portal channel."""
    ok, _ = notify("portal", "42", "Update", "Your application was updated.")
    assert ok is True
    row = NotificationOutbox.objects.latest("created_at")
    assert row.channel == "portal"


# ── acknowledgement signal tests ────────────────────────────────────────────


def test_application_create_sends_acknowledgement(tenant, application):
    """Creating an application fires an acknowledgement outbox row."""
    # The application fixture creates via ORM, triggering post_save.
    rows = NotificationOutbox.objects.filter(
        subject="Application Received",
        to=application.candidate.email,
    )
    assert rows.exists()
    row = rows.first()
    assert row.status == "sent"
    assert application.application_id in row.body
    assert application.candidate.first_name in row.body


def test_application_ack_uses_mobile_when_no_email(tenant, advertisement):
    """Acknowledgement falls back to mobile when email is empty."""
    from recruitment.models import Candidate

    candidate = Candidate.objects.create(
        first_name="Test",
        last_name="User",
        email="",
        mobile="9123456789",
    )
    post = advertisement.posts.first()
    app = Application.objects.create(post=post, candidate=candidate, status="received")

    rows = NotificationOutbox.objects.filter(subject="Application Received", to="9123456789")
    assert rows.exists()


# ── OTP via notify tests ────────────────────────────────────────────────────


def test_register_sends_otp_via_notify(tenant, api_client):
    """Registration creates an OTP notification outbox row."""
    response = api_client.post(
        reverse("portal_register"),
        {"email": "otp_test@example.com", "phone": "9876543210", "full_name": "OTP Tester"},
    )
    assert response.status_code == 302

    rows = NotificationOutbox.objects.filter(channel="sms", to="9876543210", subject="OTP")
    assert rows.exists()
    row = rows.first()
    assert "Your OTP is" in row.body
    assert row.status == "sent"

    # OTP is also still in session for verification.
    otp = api_client.session["pending_otp"]
    assert otp in row.body


# ── NotificationTemplate tests ──────────────────────────────────────────────


def test_template_render(tenant):
    """NotificationTemplate.render() substitutes placeholders."""
    tmpl = NotificationTemplate.objects.create(
        name="welcome",
        channel="email",
        subject="Welcome {name}",
        body_template="Hello {name}, your ID is {app_id}.",
    )
    rendered = tmpl.render(name="Aarav", app_id="APP-001")
    assert rendered == "Hello Aarav, your ID is APP-001."
