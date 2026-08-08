"""Phase 1 test foundation for the recruitment core app."""

from django.urls import reverse

from agents.eligibility_verifier import verify_application
from recruitment.models import (
    Application,
    AuditEvent,
    Candidate,
    CategoryAllocation,
    PanelList,
    RosterMatrix,
)
from recruitment.views import generate_offer_text


def test_application_status_flow(application):
    """Status transitions persist across save() and only use declared choices."""
    choices = dict(Application.STATUS_CHOICES)
    for status in (
        "document_verification",
        "shortlisted",
        "interview",
        "offered",
        "joined",
    ):
        assert status in choices
        application.status = status
        application.save()
        application.refresh_from_db()
        assert application.status == status


def test_roster_allocation(application):
    """Roster slots fill up and breach warnings fire past capacity."""
    matrix = RosterMatrix.objects.create(
        post=application.post, category="ur", vertical_vacancies=1
    )
    CategoryAllocation.objects.create(
        application=application, category="ur", fills_slot=True
    )
    assert matrix.filled_count == 1
    assert matrix.is_full is True
    assert matrix.breach_warning == ""

    # A second allocation for the same post/category overfills the matrix.
    second_candidate = Candidate.objects.create(
        first_name="Riya",
        last_name="Verma",
        email="riya@example.com",
        mobile="9123456780",
    )
    second_app = Application.objects.create(
        post=application.post,
        candidate=second_candidate,
        application_id="TF20260002",
    )
    CategoryAllocation.objects.create(
        application=second_app, category="ur", fills_slot=True
    )
    assert matrix.filled_count == 2
    assert "ROSTER BREACH" in matrix.breach_warning


def test_panel_promote(api_client, staff_user, application):
    """Promoting a panel entry offers the candidate and deactivates the entry."""
    entry = PanelList.objects.create(
        post=application.post, application=application, panel_rank=1, is_active=True
    )
    api_client.force_login(staff_user)  # hr_manager
    response = api_client.post(
        reverse("panel_promote", args=[application.post_id, entry.id])
    )
    assert response.status_code == 302
    application.refresh_from_db()
    assert application.status == "offered"
    entry.refresh_from_db()
    assert entry.is_active is False
    assert entry.promoted_on is not None


def test_eligibility_verdict(application):
    """Eligibility verification is rule-based and works without an API key."""
    verdict = verify_application(application)
    assert {
        "application_id",
        "post",
        "cutoff",
        "flags",
        "eligible",
        "verdict",
        "checked_at",
    } <= set(verdict)
    assert verdict["application_id"] == application.application_id
    flags = verdict["flags"]
    assert "age" in flags
    assert "qualification" in flags
    # The fixture post has no max_age, so the age check passes trivially.
    assert flags["age"]["ok"] is True
    # Qualification is a placeholder awaiting manual review.
    assert flags["qualification"]["ok"] is None
    assert isinstance(verdict["eligible"], bool)
    assert verdict["verdict"] in ("Proceed", "Review required")


def test_offer_text_generation(application):
    """Offer letter text carries the application id, post name and advt number."""
    text = generate_offer_text(application)
    assert application.application_id in text
    assert application.post.name in text
    assert application.post.advertisement.advt_number in text


def test_application_id_sanitized(application):
    """Application ids keep only [A-Za-z0-9_-]; symbols and spaces are stripped.

    Note: underscores (and hyphens) are part of the allowed set, so they are
    preserved — the stored id below keeps the two underscores.
    """
    candidate = Candidate.objects.create(
        first_name="Sam",
        last_name="Pillai",
        email="sam@example.com",
        mobile="9000000000",
    )
    app = Application.objects.create(
        post=application.post,
        candidate=candidate,
        application_id="APP!!/123 __X",
    )
    assert app.application_id == "APP123__X"


def test_application_audit_written(application):
    """Changing an application status via save() writes an audit trail row."""
    application.status = "shortlisted"
    application.save()
    event = AuditEvent.objects.filter(
        application=application, field_name="status"
    ).first()
    assert event is not None
    assert event.old_value == "received"
    assert event.new_value == "shortlisted"
    assert event.tenant_schema  # schema name recorded as the tenant identity
