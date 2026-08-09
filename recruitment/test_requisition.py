"""Tests for VacancyRequisition and RequisitionApproval models."""

from django.contrib.auth import get_user_model

from recruitment.models import RequisitionApproval, VacancyRequisition

User = get_user_model()


def _make_user(username="req_user"):
    return User.objects.create_user(
        username=username,
        password="pass",
        email=f"{username}@neepco.local",
    )


def test_vacancy_requisition_create(tenant):
    """VacancyRequisition can be created with all required fields."""
    user = _make_user()
    req = VacancyRequisition.objects.create(
        post_name="Senior Engineer",
        count=3,
        grade="E-5",
        justification="Expansion of R&D team for new project.",
        created_by=user,
    )
    assert req.pk is not None
    assert req.post_name == "Senior Engineer"
    assert req.count == 3
    assert req.grade == "E-5"
    assert req.status == "draft"  # default
    assert req.created_by == user
    assert req.created_at is not None


def test_vacancy_requisition_str(tenant):
    """VacancyRequisition __str__ shows post_name and count."""
    req = VacancyRequisition.objects.create(
        post_name="Analyst",
        count=2,
        grade="E-3",
        justification="Backfill.",
    )
    assert "Analyst" in str(req)


def test_requisition_approval_fk_round_trip(tenant):
    """RequisitionApproval links to VacancyRequisition via FK and round-trips."""
    user = _make_user("approver1")
    req = VacancyRequisition.objects.create(
        post_name="Manager",
        count=1,
        grade="E-6",
        justification="New department head.",
        created_by=user,
    )
    approval = RequisitionApproval.objects.create(
        requisition=req,
        stage="hod",
        approver=user,
        decision="approved",
        comments="Looks good, approved.",
    )
    assert approval.pk is not None
    assert approval.requisition == req
    assert approval.stage == "hod"
    assert approval.decision == "approved"
    assert approval.approver == user
    assert approval.timestamp is not None

    # reverse relation
    assert req.approvals.count() == 1
    assert req.approvals.first() == approval


def test_requisition_approval_multiple_stages(tenant):
    """Multiple approvals at different stages can exist for one requisition."""
    user_a = _make_user("approver_a")
    user_b = _make_user("approver_b")
    req = VacancyRequisition.objects.create(
        post_name="Director",
        count=1,
        grade="E-7",
        justification="Strategic hire.",
    )
    RequisitionApproval.objects.create(
        requisition=req,
        stage="hod",
        approver=user_a,
        decision="approved",
        comments="Approved at HOD level.",
    )
    RequisitionApproval.objects.create(
        requisition=req,
        stage="hr",
        approver=user_b,
        decision="approved",
        comments="Approved at HR level.",
    )
    assert req.approvals.count() == 2
    stages = set(req.approvals.values_list("stage", flat=True))
    assert stages == {"hod", "hr"}


# ── View-level tests for the requisition approval workflow ──────────────────

from django.test import Client
from django.urls import reverse

from conftest import TENANT_DOMAIN, make_staff_user, create_tenant
from recruitment.models import AuditEvent


def _client(user):
    """Return a test client logged in as *user* on the tenant domain."""
    c = Client(HTTP_HOST=TENANT_DOMAIN)
    c.force_login(user)
    return c


def test_create_requisition_as_hr_manager(tenant, staff_user):
    """HR manager can create a requisition; initial status is draft."""
    c = _client(staff_user)
    resp = c.post(reverse("requisition_create"), {
        "post_name": "Safety Officer",
        "count": "2",
        "grade": "E-4",
        "justification": "New plant opening requires dedicated safety staff.",
    })
    assert resp.status_code == 302
    req = VacancyRequisition.objects.get(post_name="Safety Officer")
    assert req.status == "draft"
    assert req.created_by == staff_user


def test_submit_requisition_transitions_to_submitted(tenant, staff_user):
    """Submitting a draft requisition changes status to submitted and creates finance stage."""
    c = _client(staff_user)
    req = VacancyRequisition.objects.create(
        post_name="Analyst", count=1, grade="E-3",
        justification="Backfill.", created_by=staff_user,
    )
    resp = c.post(reverse("requisition_detail", args=[req.pk]), {"action": "submit"})
    assert resp.status_code == 302
    req.refresh_from_db()
    assert req.status == "submitted"
    assert req.approvals.filter(stage="finance", decision="pending").exists()
    assert AuditEvent.objects.filter(field_name="requisition_status", new_value="submitted").exists()


def test_approve_finance_stage_as_recruiter(tenant, recruiter_user, staff_user):
    """Recruiter can approve the finance stage → status becomes finance_approved."""
    req = VacancyRequisition.objects.create(
        post_name="Engineer", count=2, grade="E-5",
        justification="Expansion.", status="submitted", created_by=staff_user,
    )
    RequisitionApproval.objects.create(requisition=req, stage="finance", decision="pending")

    c = _client(recruiter_user)
    resp = c.post(reverse("requisition_approve", args=[req.pk]), {
        "action": "approve",
        "comments": "Budget confirmed.",
    })
    assert resp.status_code == 302
    req.refresh_from_db()
    assert req.status == "finance_approved"
    approval = req.approvals.get(stage="finance")
    assert approval.decision == "approved"
    assert approval.approver == recruiter_user
    # Next stage (hr) should be auto-created.
    assert req.approvals.filter(stage="hr", decision="pending").exists()
    assert AuditEvent.objects.filter(field_name="requisition_status", new_value="finance_approved").exists()


def test_reject_at_finance_with_comments(tenant, recruiter_user, staff_user):
    """Rejecting a requisition at any stage requires comments and sets status to rejected."""
    req = VacancyRequisition.objects.create(
        post_name="Clerk", count=1, grade="E-2",
        justification="Temp role.", status="submitted", created_by=staff_user,
    )
    RequisitionApproval.objects.create(requisition=req, stage="finance", decision="pending")

    c = _client(recruiter_user)
    # Without comments → rejected, stays on page.
    resp = c.post(reverse("requisition_approve", args=[req.pk]), {
        "action": "reject",
        "comments": "",
    })
    assert resp.status_code == 302
    req.refresh_from_db()
    assert req.status == "submitted"  # unchanged

    # With comments → rejected.
    resp = c.post(reverse("requisition_approve", args=[req.pk]), {
        "action": "reject",
        "comments": "Insufficient budget this quarter.",
    })
    assert resp.status_code == 302
    req.refresh_from_db()
    assert req.status == "rejected"
    approval = req.approvals.get(stage="finance")
    assert approval.decision == "rejected"
    assert approval.comments == "Insufficient budget this quarter."
    assert AuditEvent.objects.filter(field_name="requisition_status", new_value="rejected").exists()
