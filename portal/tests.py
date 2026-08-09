"""Candidate portal test foundation — registration, OTP login, apply, withdraw."""

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from consent.models import Consent
from portal.models import CandidatePortalUser
from profiles.models import ExamDisclosure
from recruitment.models import Application

# CandidatePortalUser is a separate model from accounts.User, so force_login
# must pin the portal backend or the session user cannot be reloaded.
PORTAL_BACKEND = "portal.backends.CandidatePortalBackend"

RESUME_TEXT = (
    b"Name: Aarav Sharma\nEmail: aarav@example.com\nPhone: 9876543210\n"
    b"B.Tech Engineering\n2019 - Present | Assistant Manager | NEEPCO\n"
)


def _resume(filename="resume.txt"):
    return SimpleUploadedFile(filename, RESUME_TEXT, content_type="text/plain")


def test_candidate_register_login(api_client):
    """Registration stores a simulated OTP; verifying it authenticates."""
    response = api_client.post(
        reverse("portal_register"),
        {"email": "cand@example.com", "phone": "9876543210", "full_name": "Riya Verma"},
    )
    assert response.status_code == 302
    assert response.url == reverse("portal_verify")

    otp = api_client.session["pending_otp"]
    assert otp  # simulated OTP is held in the session

    response = api_client.post(reverse("portal_verify"), {"otp": otp})
    assert response.status_code == 302

    user = CandidatePortalUser.objects.get(email="cand@example.com")
    assert user.otp_verified is True

    # The session now belongs to the candidate portal user.
    response = api_client.get(reverse("portal_dashboard"))
    assert response.status_code == 200


def test_apply_flow(api_client, candidate_portal_user, advertisement):
    """A portal user can apply to a post with a resume + declaration."""
    api_client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)
    post = advertisement.posts.first()
    response = api_client.post(
        reverse("portal_apply", args=[advertisement.id]),
        {"post": post.id, "resume": _resume(), "declare": "on"},
    )
    assert response.status_code == 302

    application = Application.objects.get(
        post=post, candidate__portal_user=candidate_portal_user
    )
    assert application.status == "received"
    assert Consent.objects.filter(
        candidate_portal_user=candidate_portal_user, application=application
    ).exists()


def test_withdraw(api_client, candidate_portal_user, application):
    """Withdrawing records the terminal status and the stage it happened at."""
    application.candidate.portal_user = candidate_portal_user
    application.candidate.save()
    application.status = "document_verification"
    application.save()

    api_client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)
    response = api_client.post(
        reverse("portal_application_withdraw", args=[application.application_id])
    )
    assert response.status_code == 302
    application.refresh_from_db()
    assert application.status == "withdrawn"
    assert application.rejected_at_stage == "document_verification"


def test_duplicate_application_blocked(api_client, candidate_portal_user, advertisement):
    """A candidate may apply to an advertisement only once, across any post."""
    api_client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)
    first_post, second_post = advertisement.posts.all()[:2]

    response = api_client.post(
        reverse("portal_apply", args=[advertisement.id]),
        {"post": first_post.id, "resume": _resume(), "declare": "on"},
    )
    assert response.status_code == 302

    base_qs = Application.objects.filter(
        candidate__portal_user=candidate_portal_user,
        post__advertisement=advertisement,
    )
    assert base_qs.count() == 1

    # Applying against a *different* post of the same advertisement is blocked.
    response = api_client.post(
        reverse("portal_apply", args=[advertisement.id]),
        {"post": second_post.id, "resume": _resume("resume2.txt"), "declare": "on"},
    )
    assert response.status_code == 302
    existing = base_qs.get()
    assert response.url == reverse(
        "portal_application_detail", args=[existing.application_id]
    )
    assert base_qs.count() == 1


def test_profile_save_with_blank_exam_fields(api_client, candidate_portal_user):
    """The profile template renders None as value=\"None\"; saving must not crash.

    Regression: POSTing the literal string "None" for numeric/date fields used
    to raise ValueError/ValidationError on ExamDisclosure.save().
    """
    api_client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)
    response = api_client.post(
        reverse("portal_profile"),
        {
            "gate_year": "None",
            "paper_code": "",
            "marks_out_100": "None",
            "gate_score": "None",
            "air": "None",
            "ese_total_score": "None",
            "work_start_0": "None",
            "work_end_0": "None",
        },
    )
    assert response.status_code == 302
    exam = ExamDisclosure.objects.get(candidate__portal_user=candidate_portal_user)
    assert exam.gate_year is None
    assert exam.gate_score is None
    assert exam.air is None
    assert exam.ese_total_score is None


def test_profile_save_with_filled_exam_fields(api_client, candidate_portal_user):
    """Valid numeric exam values survive the round trip."""
    api_client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)
    response = api_client.post(
        reverse("portal_profile"),
        {
            "exam_type": "gate",
            "gate_year": "2024",
            "paper_code": "CE",
            "marks_out_100": "67.5",
            "gate_score": "98.5",
            "air": "42",
            "ese_total_score": "111.25",
        },
    )
    assert response.status_code == 302
    exam = ExamDisclosure.objects.get(candidate__portal_user=candidate_portal_user)
    assert exam.gate_year == 2024
    assert exam.gate_score == Decimal("98.5")
    assert exam.marks_out_100 == Decimal("67.5")
    assert exam.air == 42
    assert exam.ese_total_score == Decimal("111.25")


def test_slip_pdf_download(api_client, candidate_portal_user, application):
    application.candidate.portal_user = candidate_portal_user
    application.candidate.save()
    api_client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)
    r = api_client.get(reverse("portal_application_slip", args=[application.application_id]))
    assert r.status_code == 200
    assert r["Content-Type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF")


def test_slip_contains_application_data(api_client, candidate_portal_user, application):
    application.candidate.portal_user = candidate_portal_user
    application.candidate.save()
    api_client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)
    import io
    from django.test import Client
    from agents import doc_intel
    r = api_client.get(reverse("portal_application_slip", args=[application.application_id]))
    p = io.BytesIO(r.content)
    # write to temp for doc_intel (needs a path); mkstemp's fd must be closed
    # or Windows keeps the file locked and unlink() fails (WinError 32).
    import tempfile, pathlib, os
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    path = pathlib.Path(tmp); path.write_bytes(r.content)
    text = doc_intel.extract_text(str(path)); path.unlink()
    assert application.application_id in text
    assert "no document is required to be sent by post" in text.lower()


def test_slip_owner_only(api_client, tenant, application):
    from portal.models import CandidatePortalUser
    other = CandidatePortalUser.objects.create(email="other@example.com", otp_verified=True)
    api_client.force_login(other, backend=PORTAL_BACKEND)
    r = api_client.get(reverse("portal_application_slip", args=[application.application_id]))
    assert r.status_code in (302, 403)
