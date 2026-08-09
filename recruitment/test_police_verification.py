"""Tests for PoliceVerification — model, views, and audit trail."""

from django.contrib.auth import get_user_model
from django.urls import reverse

from recruitment.models import AuditEvent, PoliceVerification

User = get_user_model()


def _make_user(username, role="recruiter"):
    return User.objects.create_user(
        username=username,
        password="pass",
        email=f"{username}@neepco.local",
    )


# ── Model tests ─────────────────────────────────────────────────────────────


def test_police_verification_create(tenant, application):
    """PoliceVerification can be created with required fields."""
    pv = PoliceVerification.objects.create(
        application=application,
        district="East Khasi Hills",
    )
    assert pv.pk is not None
    assert pv.district == "East Khasi Hills"
    assert pv.status == "initiated"  # default
    assert pv.report_file.name == ""
    assert pv.initiated_by is None
    assert pv.notes == ""
    assert pv.created_at is not None


def test_police_verification_str(tenant, application):
    """__str__ shows application id, district, and status display."""
    pv = PoliceVerification.objects.create(
        application=application,
        district="Ri-Bhoi",
        status="in_progress",
    )
    s = str(pv)
    assert application.application_id in s
    assert "Ri-Bhoi" in s
    assert "In Progress" in s


def test_police_verification_status_choices(tenant, application):
    """All four status choices are valid."""
    for status_key, _label in PoliceVerification._meta.get_field("status").choices:
        pv = PoliceVerification.objects.create(
            application=application,
            district="Test District",
            status=status_key,
        )
        assert pv.status == status_key
        pv.delete()


def test_police_verification_application_relation(tenant, application):
    """Reverse relation from application works."""
    PoliceVerification.objects.create(application=application, district="District A")
    PoliceVerification.objects.create(application=application, district="District B")
    assert application.police_verifications.count() == 2


def test_police_verification_initiated_by(tenant, application, staff_user):
    """initiated_by links to the staff user who started the verification."""
    pv = PoliceVerification.objects.create(
        application=application,
        district="West Garo Hills",
        initiated_by=staff_user,
    )
    assert pv.initiated_by == staff_user
    assert staff_user.initiated_police_verifications.count() == 1


# ── View tests ──────────────────────────────────────────────────────────────


def test_police_verification_initiate_hr_manager(api_client, staff_user, application):
    """HR manager can initiate a police verification."""
    api_client.force_login(staff_user)
    url = reverse("police_verification_initiate", args=[application.application_id])
    resp = api_client.post(url, {"district": "East Khasi Hills", "notes": "Urgent"})
    assert resp.status_code == 302
    pv = PoliceVerification.objects.get(application=application)
    assert pv.district == "East Khasi Hills"
    assert pv.status == "initiated"
    assert pv.initiated_by == staff_user
    assert pv.notes == "Urgent"


def test_police_verification_initiate_requires_district(api_client, staff_user, application):
    """Initiating without a district shows error and does not create."""
    api_client.force_login(staff_user)
    url = reverse("police_verification_initiate", args=[application.application_id])
    resp = api_client.post(url, {"district": ""})
    assert resp.status_code == 302
    assert PoliceVerification.objects.count() == 0


def test_police_verification_initiate_requires_hr_manager(api_client, recruiter_user, application):
    """Non-hr_manager roles cannot initiate."""
    api_client.force_login(recruiter_user)
    url = reverse("police_verification_initiate", args=[application.application_id])
    resp = api_client.post(url, {"district": "Test"})
    assert resp.status_code == 403
    assert PoliceVerification.objects.count() == 0


def test_police_verification_update_status_recruiter(api_client, recruiter_user, application):
    """Recruiter can update police verification status."""
    pv = PoliceVerification.objects.create(
        application=application,
        district="East Khasi Hills",
    )
    api_client.force_login(recruiter_user)
    url = reverse("police_verification_update_status", args=[pv.pk])
    resp = api_client.post(url, {"status": "in_progress", "notes": "Under review"})
    assert resp.status_code == 302
    pv.refresh_from_db()
    assert pv.status == "in_progress"
    assert pv.notes == "Under review"


def test_police_verification_update_status_to_cleared(api_client, recruiter_user, application):
    """Recruiter can mark verification as cleared."""
    pv = PoliceVerification.objects.create(
        application=application,
        district="Ri-Bhoi",
        status="in_progress",
    )
    api_client.force_login(recruiter_user)
    url = reverse("police_verification_update_status", args=[pv.pk])
    resp = api_client.post(url, {"status": "cleared"})
    assert resp.status_code == 302
    pv.refresh_from_db()
    assert pv.status == "cleared"


def test_police_verification_update_status_invalid(api_client, recruiter_user, application):
    """Invalid status is rejected."""
    pv = PoliceVerification.objects.create(
        application=application,
        district="Test",
    )
    api_client.force_login(recruiter_user)
    url = reverse("police_verification_update_status", args=[pv.pk])
    resp = api_client.post(url, {"status": "bogus"})
    assert resp.status_code == 302
    pv.refresh_from_db()
    assert pv.status == "initiated"  # unchanged


def test_police_verification_update_status_requires_recruiter(api_client, staff_user, application):
    """Non-recruiter roles cannot update status."""
    pv = PoliceVerification.objects.create(
        application=application,
        district="Test",
    )
    api_client.force_login(staff_user)  # hr_manager, not recruiter
    url = reverse("police_verification_update_status", args=[pv.pk])
    resp = api_client.post(url, {"status": "cleared"})
    assert resp.status_code == 403
    pv.refresh_from_db()
    assert pv.status == "initiated"


# ── Audit trail tests ───────────────────────────────────────────────────────


def test_police_verification_initiate_audits(api_client, staff_user, application):
    """Initiating a police verification writes an AuditEvent."""
    api_client.force_login(staff_user)
    url = reverse("police_verification_initiate", args=[application.application_id])
    api_client.post(url, {"district": "East Khasi Hills"})

    event = AuditEvent.objects.filter(
        application=application,
        field_name="police_verification",
    ).first()
    assert event is not None
    assert event.new_value == "initiated"
    assert event.actor == staff_user
    assert "East Khasi Hills" in event.reason


def test_police_verification_status_change_audits(api_client, recruiter_user, application):
    """Updating police verification status writes an AuditEvent."""
    pv = PoliceVerification.objects.create(
        application=application,
        district="Ri-Bhoi",
    )
    api_client.force_login(recruiter_user)
    url = reverse("police_verification_update_status", args=[pv.pk])
    api_client.post(url, {"status": "cleared"})

    event = AuditEvent.objects.filter(
        application=application,
        field_name="police_verification_status",
    ).first()
    assert event is not None
    assert event.old_value == "initiated"
    assert event.new_value == "cleared"
    assert event.actor == recruiter_user


def test_police_verification_no_audit_on_same_status(api_client, recruiter_user, application):
    """No audit event when status doesn't actually change."""
    pv = PoliceVerification.objects.create(
        application=application,
        district="Test",
        status="initiated",
    )
    api_client.force_login(recruiter_user)
    url = reverse("police_verification_update_status", args=[pv.pk])
    api_client.post(url, {"status": "initiated"})

    assert AuditEvent.objects.filter(
        application=application,
        field_name="police_verification_status",
    ).count() == 0
