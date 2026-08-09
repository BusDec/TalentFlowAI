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
