"""Tests for Grievance — candidate grievance/appeal filing + resolution workflow."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from conftest import TENANT_DOMAIN, create_tenant, make_staff_user
from portal.models import CandidatePortalUser
from recruitment.models import (
    Advertisement,
    Application,
    Candidate,
    Grievance,
    Post,
)

User = get_user_model()

PORTAL_BACKEND = "portal.backends.CandidatePortalBackend"


def _make_candidate(tenant, portal_user=None):
    """Create a candidate with optional portal user link."""
    candidate = Candidate.objects.create(
        first_name="Grievance",
        last_name="Tester",
        email="grievance@test.com",
        mobile="9000000001",
    )
    if portal_user:
        candidate.portal_user = portal_user
        candidate.save(update_fields=["portal_user"])
    return candidate


def _make_application(tenant, candidate, advertisement):
    """Create a minimal application."""
    post = advertisement.posts.first()
    return Application.objects.create(
        application_id="GRV-APP-001",
        candidate=candidate,
        post=post,
    )


# ── Model tests ─────────────────────────────────────────────────────────────


def test_grievance_create(tenant):
    """Grievance can be created with all required fields."""
    candidate = _make_candidate(tenant)
    g = Grievance.objects.create(
        candidate=candidate,
        subject="Incorrect category",
        description="My category was wrongly marked as OBC instead of General.",
    )
    assert g.pk is not None
    assert g.status == "filed"
    assert g.assigned_to is None
    assert g.application is None
    assert g.resolution_notes == ""
    assert g.created_at is not None


def test_grievance_str(tenant):
    """__str__ shows candidate and subject."""
    candidate = _make_candidate(tenant)
    g = Grievance.objects.create(
        candidate=candidate,
        subject="Missing marks",
        description="My written exam marks are not showing.",
    )
    s = str(g)
    assert "Grievance Tester" in s
    assert "Missing marks" in s


def test_grievance_with_application_fk(tenant, advertisement):
    """Grievance can optionally link to an application."""
    candidate = _make_candidate(tenant)
    app = _make_application(tenant, candidate, advertisement)
    g = Grievance.objects.create(
        candidate=candidate,
        application=app,
        subject="Wrong post allocation",
        description="I was allocated to wrong post.",
    )
    assert g.application == app
    assert app.grievances.count() == 1


def test_grievance_status_choices(tenant):
    """Status defaults to 'filed' and can transition through all states."""
    candidate = _make_candidate(tenant)
    g = Grievance.objects.create(
        candidate=candidate,
        subject="Test status",
        description="Testing status transitions.",
    )
    for status, _label in Grievance._meta.get_field("status").choices:
        g.status = status
        g.save(update_fields=["status"])
        g.refresh_from_db()
        assert g.status == status


def test_grievance_application_null_on_delete(tenant, advertisement):
    """Application FK is SET_NULL when the application is deleted."""
    candidate = _make_candidate(tenant)
    app = _make_application(tenant, candidate, advertisement)
    g = Grievance.objects.create(
        candidate=candidate,
        application=app,
        subject="FK test",
        description="Testing SET_NULL.",
    )
    app.delete()
    g.refresh_from_db()
    assert g.application is None


def test_grievance_ordering(tenant):
    """Grievances are ordered by -created_at (newest first)."""
    candidate = _make_candidate(tenant)
    g1 = Grievance.objects.create(candidate=candidate, subject="First", description="First filed.")
    g2 = Grievance.objects.create(candidate=candidate, subject="Second", description="Second filed.")
    grievances = list(Grievance.objects.all())
    assert grievances[0] == g2
    assert grievances[1] == g1


# ── Portal view tests ───────────────────────────────────────────────────────


def test_portal_file_grievance_creates(tenant, candidate_portal_user):
    """Candidate can file a grievance via the portal."""
    candidate = _make_candidate(tenant, portal_user=candidate_portal_user)
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)

    response = client.post("/portal/grievances/file/", {
        "subject": "Exam centre issue",
        "description": "I was assigned to a centre 200km away.",
    })
    assert response.status_code == 302
    assert Grievance.objects.filter(subject="Exam centre issue").exists()


def test_portal_file_grievance_with_application(tenant, candidate_portal_user, advertisement):
    """Candidate can link a grievance to an application."""
    candidate = _make_candidate(tenant, portal_user=candidate_portal_user)
    app = _make_application(tenant, candidate, advertisement)
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)

    response = client.post("/portal/grievances/file/", {
        "subject": "Wrong post",
        "description": "Wrong allocation.",
        "application_id": app.application_id,
    })
    assert response.status_code == 302
    g = Grievance.objects.get(subject="Wrong post")
    assert g.application == app


def test_portal_file_grievance_requires_subject(tenant, candidate_portal_user):
    """Filing without subject shows error."""
    candidate = _make_candidate(tenant, portal_user=candidate_portal_user)
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)

    response = client.post("/portal/grievances/file/", {
        "subject": "",
        "description": "Some description.",
    })
    assert response.status_code == 200  # re-renders form
    assert not Grievance.objects.exists()


def test_portal_my_grievances_lists(tenant, candidate_portal_user):
    """My grievances page lists only the candidate's grievances."""
    candidate = _make_candidate(tenant, portal_user=candidate_portal_user)
    Grievance.objects.create(candidate=candidate, subject="G1", description="Desc 1")
    Grievance.objects.create(candidate=candidate, subject="G2", description="Desc 2")

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(candidate_portal_user, backend=PORTAL_BACKEND)
    response = client.get("/portal/grievances/")
    content = response.content.decode()
    assert "G1" in content
    assert "G2" in content


def test_portal_file_grievance_requires_auth(tenant):
    """Unauthenticated users are redirected to login."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    response = client.get("/portal/grievances/file/")
    assert response.status_code == 302


# ── Staff view tests ────────────────────────────────────────────────────────


def test_grievance_list_view(tenant, staff_user):
    """HR manager can view the grievance list."""
    candidate = _make_candidate(tenant)
    Grievance.objects.create(candidate=candidate, subject="Listed grievance", description="Test.")

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.get("/grievances/")
    assert response.status_code == 200
    assert "Listed grievance" in response.content.decode()


def test_grievance_list_filter_by_status(tenant, staff_user):
    """Grievance list can be filtered by status."""
    candidate = _make_candidate(tenant)
    Grievance.objects.create(candidate=candidate, subject="Filed one", description=".", status="filed")
    Grievance.objects.create(candidate=candidate, subject="Resolved one", description=".", status="resolved")

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.get("/grievances/?status=resolved")
    content = response.content.decode()
    assert "Resolved one" in content
    assert "Filed one" not in content


def test_grievance_assign_view(tenant, staff_user):
    """Staff can assign a grievance to themselves."""
    candidate = _make_candidate(tenant)
    g = Grievance.objects.create(candidate=candidate, subject="Assign me", description=".")

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.post(f"/grievances/{g.pk}/assign/")
    assert response.status_code == 302

    g.refresh_from_db()
    assert g.assigned_to == staff_user
    assert g.status == "acknowledged"  # auto-updates from filed


def test_grievance_update_status(tenant, staff_user):
    """Staff can update grievance status."""
    candidate = _make_candidate(tenant)
    g = Grievance.objects.create(candidate=candidate, subject="Update me", description=".")

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.post(f"/grievances/{g.pk}/update-status/", {
        "status": "investigating",
        "resolution_notes": "",
    })
    assert response.status_code == 302

    g.refresh_from_db()
    assert g.status == "investigating"


def test_grievance_resolve_with_notes(tenant, staff_user):
    """Resolving a grievance saves resolution notes."""
    candidate = _make_candidate(tenant)
    g = Grievance.objects.create(candidate=candidate, subject="Resolve me", description=".")

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.post(f"/grievances/{g.pk}/update-status/", {
        "status": "resolved",
        "resolution_notes": "Category corrected in the system.",
    })
    assert response.status_code == 302

    g.refresh_from_db()
    assert g.status == "resolved"
    assert g.resolution_notes == "Category corrected in the system."


def test_grievance_update_invalid_status(tenant, staff_user):
    """Invalid status value is rejected."""
    candidate = _make_candidate(tenant)
    g = Grievance.objects.create(candidate=candidate, subject="Bad status", description=".")

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.post(f"/grievances/{g.pk}/update-status/", {"status": "invalid"})
    assert response.status_code == 302

    g.refresh_from_db()
    assert g.status == "filed"  # unchanged


# ── Notification tests ──────────────────────────────────────────────────────


def test_acknowledge_sends_notification(tenant, staff_user):
    """Acknowledging a filed grievance sends a notification to the candidate."""
    candidate = _make_candidate(tenant)
    g = Grievance.objects.create(candidate=candidate, subject="Notify me", description=".")

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)

    with patch("recruitment.views.send_notification") as mock_notify:
        mock_notify.return_value = (True, "sent")
        response = client.post(f"/grievances/{g.pk}/update-status/", {
            "status": "acknowledged",
        })
        assert response.status_code == 302
        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args
        assert call_kwargs[1]["subject"] == f"Grievance Acknowledged — Notify me"


def test_non_acknowledge_status_no_notification(tenant, staff_user):
    """Moving to 'investigating' does not trigger a notification."""
    candidate = _make_candidate(tenant)
    g = Grievance.objects.create(candidate=candidate, subject="No notify", description=".", status="acknowledged")

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)

    with patch("recruitment.views.send_notification") as mock_notify:
        client.post(f"/grievances/{g.pk}/update-status/", {"status": "investigating"})
        mock_notify.assert_not_called()


# ── Permission tests ────────────────────────────────────────────────────────


def test_grievance_list_requires_staff_auth(tenant):
    """Unauthenticated users cannot access the staff grievance list."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    response = client.get("/grievances/")
    assert response.status_code == 302  # redirect to login


def test_viewer_cannot_update_grievance(tenant, viewer_user):
    """Viewer role cannot update grievance status."""
    candidate = _make_candidate(tenant)
    g = Grievance.objects.create(candidate=candidate, subject="No access", description=".")

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(viewer_user)
    response = client.post(f"/grievances/{g.pk}/update-status/", {"status": "acknowledged"})
    assert response.status_code == 403
