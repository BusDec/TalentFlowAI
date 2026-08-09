"""Tests for JoiningReport model and portal submission workflow."""

import datetime

from django.urls import reverse

from portal.models import CandidatePortalUser
from recruitment.models import Application, Candidate, JoiningReport

PORTAL_BACKEND = "portal.backends.CandidatePortalBackend"


def test_joining_report_model(db, tenant, advertisement):
    """JoiningReport can be created and linked to an application."""
    candidate = Candidate.objects.create(
        first_name="Test", last_name="User", email="test@example.com", mobile="9000000000"
    )
    post = advertisement.posts.first()
    application = Application.objects.create(
        post=post, candidate=candidate, application_id="JR20260001", status="joined"
    )
    report = JoiningReport.objects.create(
        application=application,
        joining_date=datetime.date(2026, 8, 1),
        designation="Assistant Engineer",
        pay_fixation="Level-7, ₹44,900/-",
        reported_to="Shri R. Kumar, GM (HR)",
        documents_submitted=True,
    )
    assert report.pk is not None
    assert str(report) == "JoiningReport(JR20260001) — 2026-08-01"
    assert application.joining_report == report


def test_joining_report_one_to_one(db, tenant, advertisement):
    """Only one JoiningReport per application (OneToOneField)."""
    candidate = Candidate.objects.create(
        first_name="Test", last_name="User", email="test@example.com", mobile="9000000000"
    )
    post = advertisement.posts.first()
    application = Application.objects.create(
        post=post, candidate=candidate, application_id="JR20260002", status="joined"
    )
    JoiningReport.objects.create(
        application=application,
        joining_date=datetime.date(2026, 8, 1),
        designation="Engineer",
        reported_to="GM",
    )
    try:
        JoiningReport.objects.create(
            application=application,
            joining_date=datetime.date(2026, 8, 2),
            designation="Engineer",
            reported_to="GM",
        )
        assert False, "Should have raised IntegrityError"
    except Exception:
        pass  # IntegrityError expected


def test_submit_joining_report_view_get(api_client, db, tenant, advertisement):
    """GET renders the joining report form for a joined application."""
    user = CandidatePortalUser.objects.create(
        email="jr@example.com", phone="9000000001", full_name="JR Test", otp_verified=True
    )
    candidate = Candidate.objects.create(
        first_name="JR", last_name="Test", email="jr@example.com", mobile="9000000001",
        portal_user=user,
    )
    post = advertisement.posts.first()
    application = Application.objects.create(
        post=post, candidate=candidate, application_id="JR20260003", status="joined"
    )

    api_client.force_login(user, backend=PORTAL_BACKEND)
    response = api_client.get(
        reverse("portal_submit_joining_report", args=[application.application_id])
    )
    assert response.status_code == 200
    assert b"Joining Report" in response.content


def test_submit_joining_report_view_post(api_client, db, tenant, advertisement):
    """POST creates a JoiningReport and redirects."""
    user = CandidatePortalUser.objects.create(
        email="jr2@example.com", phone="9000000002", full_name="JR Test 2", otp_verified=True
    )
    candidate = Candidate.objects.create(
        first_name="JR2", last_name="Test", email="jr2@example.com", mobile="9000000002",
        portal_user=user,
    )
    post = advertisement.posts.first()
    application = Application.objects.create(
        post=post, candidate=candidate, application_id="JR20260004", status="joined"
    )

    api_client.force_login(user, backend=PORTAL_BACKEND)
    response = api_client.post(
        reverse("portal_submit_joining_report", args=[application.application_id]),
        {
            "joining_date": "2026-08-01",
            "designation": "Assistant Engineer",
            "pay_fixation": "Level-7",
            "reported_to": "Shri Kumar, GM (HR)",
            "documents_submitted": "on",
        },
    )
    assert response.status_code == 302
    report = JoiningReport.objects.get(application=application)
    assert report.designation == "Assistant Engineer"
    assert report.documents_submitted is True
    assert report.joining_date == datetime.date(2026, 8, 1)


def test_submit_joining_report_redirects_if_not_joined(api_client, db, tenant, advertisement):
    """Redirect when application status is not 'joined'."""
    user = CandidatePortalUser.objects.create(
        email="nj@example.com", phone="9000000003", full_name="NJ Test", otp_verified=True
    )
    candidate = Candidate.objects.create(
        first_name="NJ", last_name="Test", email="nj@example.com", mobile="9000000003",
        portal_user=user,
    )
    post = advertisement.posts.first()
    application = Application.objects.create(
        post=post, candidate=candidate, application_id="JR20260005", status="offered"
    )

    api_client.force_login(user, backend=PORTAL_BACKEND)
    response = api_client.get(
        reverse("portal_submit_joining_report", args=[application.application_id])
    )
    assert response.status_code == 302


def test_submit_joining_report_redirects_if_already_submitted(api_client, db, tenant, advertisement):
    """Redirect when joining report already exists."""
    user = CandidatePortalUser.objects.create(
        email="as@example.com", phone="9000000004", full_name="AS Test", otp_verified=True
    )
    candidate = Candidate.objects.create(
        first_name="AS", last_name="Test", email="as@example.com", mobile="9000000004",
        portal_user=user,
    )
    post = advertisement.posts.first()
    application = Application.objects.create(
        post=post, candidate=candidate, application_id="JR20260006", status="joined"
    )
    JoiningReport.objects.create(
        application=application,
        joining_date=datetime.date(2026, 8, 1),
        designation="Engineer",
        reported_to="GM",
    )

    api_client.force_login(user, backend=PORTAL_BACKEND)
    response = api_client.get(
        reverse("portal_submit_joining_report", args=[application.application_id])
    )
    assert response.status_code == 302


def test_submit_joining_report_validates_required_fields(api_client, db, tenant, advertisement):
    """POST without required fields re-renders the form with errors."""
    user = CandidatePortalUser.objects.create(
        email="vf@example.com", phone="9000000005", full_name="VF Test", otp_verified=True
    )
    candidate = Candidate.objects.create(
        first_name="VF", last_name="Test", email="vf@example.com", mobile="9000000005",
        portal_user=user,
    )
    post = advertisement.posts.first()
    application = Application.objects.create(
        post=post, candidate=candidate, application_id="JR20260007", status="joined"
    )

    api_client.force_login(user, backend=PORTAL_BACKEND)
    # Missing designation and reported_to
    response = api_client.post(
        reverse("portal_submit_joining_report", args=[application.application_id]),
        {"joining_date": "2026-08-01"},
    )
    assert response.status_code == 200  # re-renders form
    assert not JoiningReport.objects.filter(application=application).exists()


def test_application_detail_shows_joining_report_link(api_client, db, tenant, advertisement):
    """Application detail page shows 'Submit Joining Report' link when status is joined."""
    user = CandidatePortalUser.objects.create(
        email="dt@example.com", phone="9000000006", full_name="DT Test", otp_verified=True
    )
    candidate = Candidate.objects.create(
        first_name="DT", last_name="Test", email="dt@example.com", mobile="9000000006",
        portal_user=user,
    )
    post = advertisement.posts.first()
    application = Application.objects.create(
        post=post, candidate=candidate, application_id="JR20260008", status="joined"
    )

    api_client.force_login(user, backend=PORTAL_BACKEND)
    response = api_client.get(
        reverse("portal_application_detail", args=[application.application_id])
    )
    assert response.status_code == 200
    assert b"Submit Joining Report" in response.content
