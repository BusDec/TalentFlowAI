"""Autofill (Phase 2) — document parsing, session prefill, confirm gate, badges."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

# CandidatePortalUser is a separate model from accounts.User, so force_login
# must pin the portal backend or the session user cannot be reloaded.
PORTAL_BACKEND = "portal.backends.CandidatePortalBackend"

PAN_TEXT = b"INCOME TAX DEPARTMENT\nPermanent Account Number\nABCDE1234F\nName: RAM KUMAR\n"
RESUME_TEXT = b"Name: Aarav Sharma\nEmail: aarav@example.com\nPhone: 9876543210\nB.Tech\n"


def test_apply_phase1_parses_and_prefills(api_client, candidate_portal_user, advertisement):
    """Phase-1 POST parses the documents, renders the prefill, creates nothing."""
    api_client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)
    r = api_client.post(
        reverse("portal_apply", args=[advertisement.id]),
        {
            "post": advertisement.posts.first().id,
            "resume": SimpleUploadedFile("r.txt", RESUME_TEXT, content_type="text/plain"),
            "cert_0": SimpleUploadedFile("pan.txt", PAN_TEXT, content_type="text/plain"),
        },
    )
    assert r.status_code == 200
    body = r.content.decode()
    assert "auto-filled" in body.lower() and "ABCDE1234F" in body
    from recruitment.models import Application

    assert not Application.objects.filter(candidate__portal_user=candidate_portal_user).exists()


def test_apply_phase2_requires_confirm(api_client, candidate_portal_user, advertisement):
    """A prefill must be confirmed before the application is created."""
    api_client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)
    api_client.post(
        reverse("portal_apply", args=[advertisement.id]),
        {
            "post": advertisement.posts.first().id,
            "resume": SimpleUploadedFile("r.txt", RESUME_TEXT, content_type="text/plain"),
        },
    )
    r = api_client.post(
        reverse("portal_apply", args=[advertisement.id]),
        {
            "post": advertisement.posts.first().id,
            "declare": "on",
            "resume": SimpleUploadedFile("r.txt", RESUME_TEXT, content_type="text/plain"),
        },
    )
    assert r.status_code == 200  # confirm required
    from recruitment.models import Application

    assert not Application.objects.filter(candidate__portal_user=candidate_portal_user).exists()


def test_consistency_warning_shown(api_client, candidate_portal_user, advertisement):
    """Conflicting names across documents surface a consistency warning."""
    api_client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)
    r = api_client.post(
        reverse("portal_apply", args=[advertisement.id]),
        {
            "post": advertisement.posts.first().id,
            "resume": SimpleUploadedFile(
                "r.txt", b"Name: Shyam Verma\nEmail: s@x.com\n", content_type="text/plain"
            ),
            "cert_0": SimpleUploadedFile("pan.txt", PAN_TEXT, content_type="text/plain"),
        },
    )
    assert r.status_code == 200
    assert "does not match" in r.content.decode().lower() or "consisten" in r.content.decode().lower()


def test_confirm_checkbox_rendered_with_prefill(api_client, candidate_portal_user, advertisement):
    """GET after a phase-1 POST preserves the prefill and renders confirm."""
    api_client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)
    api_client.post(
        reverse("portal_apply", args=[advertisement.id]),
        {
            "post": advertisement.posts.first().id,
            "resume": SimpleUploadedFile("r.txt", b"Name: Aarav Sharma\n", content_type="text/plain"),
        },
    )
    r = api_client.get(reverse("portal_apply", args=[advertisement.id]))
    assert "confirm" in r.content.decode().lower()


def test_apply_phase2_creates_application(api_client, candidate_portal_user, advertisement):
    """Confirming a phase-1 prefill creates the application and consumes the prefill."""
    api_client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)
    session_key = f"apply_prefill_{advertisement.id}"
    api_client.post(
        reverse("portal_apply", args=[advertisement.id]),
        {
            "post": advertisement.posts.first().id,
            "resume": SimpleUploadedFile("r.txt", RESUME_TEXT, content_type="text/plain"),
        },
    )
    r = api_client.post(
        reverse("portal_apply", args=[advertisement.id]),
        {
            "post": advertisement.posts.first().id,
            "declare": "on",
            "confirm": "on",
            "resume": SimpleUploadedFile("r.txt", RESUME_TEXT, content_type="text/plain"),
        },
    )
    assert r.status_code == 302
    from recruitment.models import Application

    assert Application.objects.filter(candidate__portal_user=candidate_portal_user).exists()
    # The prefill session key is consumed by a successful submission.
    assert session_key not in api_client.session
