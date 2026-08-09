"""Tests for DocumentVerification model, signal, and views."""

from django.contrib.auth import get_user_model
from django.test import Client

from conftest import TENANT_DOMAIN
from recruitment.models import AuditEvent, Document, DocumentVerification

User = get_user_model()


def _make_user(username="recruit_user"):
    return User.objects.create_user(
        username=username,
        password="pass",
        email=f"{username}@neepco.local",
    )


# ── Model tests ──────────────────────────────────────────────────────────────


def test_document_verification_create(tenant, application):
    """DocumentVerification is auto-created via signal with all defaults."""
    doc = Document.objects.create(
        application=application,
        doc_type="degree",
        file="documents/test.pdf",
    )
    dv = doc.verification
    assert dv.pk is not None
    assert dv.document == doc
    assert dv.status == "pending"
    assert dv.verifier is None
    assert dv.comments == ""
    assert dv.verified_at is None
    assert dv.created_at is not None


def test_document_verification_str(tenant, application):
    """__str__ includes doc_type and status display."""
    doc = Document.objects.create(
        application=application,
        doc_type="marksheet",
        file="documents/marksheet.pdf",
    )
    dv = doc.verification
    s = str(dv)
    assert "marksheet" in s
    assert "Pending" in s


def test_document_verification_status_choices(tenant, application):
    """All three status choices work."""
    doc = Document.objects.create(
        application=application,
        doc_type="category_certificate",
        file="documents/cat.pdf",
    )
    dv = doc.verification
    dv.status = "verified"
    dv.save()
    assert dv.get_status_display() == "Verified"

    dv.status = "rejected"
    dv.save()
    assert dv.get_status_display() == "Rejected"


def test_document_verification_verifier_fk(tenant, application):
    """Verifier FK can be set to a staff user."""
    doc = Document.objects.create(
        application=application,
        doc_type="experience",
        file="documents/exp.pdf",
    )
    user = _make_user("verifier1")
    dv = doc.verification
    dv.status = "verified"
    dv.verifier = user
    dv.comments = "All good."
    dv.save()
    dv.refresh_from_db()
    assert dv.verifier == user
    assert dv.comments == "All good."


# ── Signal tests ─────────────────────────────────────────────────────────────


def test_auto_create_verification_on_document_creation(tenant, application):
    """Creating a Document auto-creates a pending DocumentVerification via signal."""
    doc = Document.objects.create(
        application=application,
        doc_type="dob",
        file="documents/dob.pdf",
    )
    assert hasattr(doc, "verification"), "Document should have a verification reverse relation"
    dv = doc.verification
    assert dv.status == "pending"
    assert dv.verifier is None
    assert dv.comments == ""


def test_signal_does_not_duplicate_on_save(tenant, application):
    """Re-saving a Document does not create a second DocumentVerification."""
    doc = Document.objects.create(
        application=application,
        doc_type="degree",
        file="documents/degree.pdf",
    )
    doc.save()  # re-save
    assert DocumentVerification.objects.filter(document=doc).count() == 1


# ── View tests ───────────────────────────────────────────────────────────────


def test_verify_documents_view_reachable(tenant, application, recruiter_user):
    """Recruiter can access the verify_documents page."""
    doc = Document.objects.create(
        application=application,
        doc_type="degree",
        file="documents/degree.pdf",
    )
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(recruiter_user)
    resp = client.get("/verify-documents/")
    assert resp.status_code == 200
    assert "Document Verification" in resp.content.decode()


def test_verify_action_creates_audit_event(tenant, application, recruiter_user):
    """POST verify action updates status and creates an AuditEvent."""
    doc = Document.objects.create(
        application=application,
        doc_type="degree",
        file="documents/degree.pdf",
    )
    dv = doc.verification

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(recruiter_user)
    resp = client.post("/verify-documents/", {
        "verification_id": dv.id,
        "action": "verified",
        "comments": "Looks authentic.",
    })
    assert resp.status_code == 302  # redirect

    dv.refresh_from_db()
    assert dv.status == "verified"
    assert dv.verifier == recruiter_user
    assert dv.comments == "Looks authentic."
    assert dv.verified_at is not None

    # Legacy flag updated
    doc.refresh_from_db()
    assert doc.is_verified is True

    # Audit event written
    audit = AuditEvent.objects.filter(
        application=application,
        field_name="document_verification",
    ).first()
    assert audit is not None
    assert audit.old_value == "pending"
    assert audit.new_value == "verified"


def test_reject_action_creates_audit_event(tenant, application, recruiter_user):
    """POST reject action sets rejected status and creates an AuditEvent."""
    doc = Document.objects.create(
        application=application,
        doc_type="marksheet",
        file="documents/marksheet.pdf",
    )
    dv = doc.verification

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(recruiter_user)
    resp = client.post("/verify-documents/", {
        "verification_id": dv.id,
        "action": "rejected",
        "comments": "Blurry scan.",
    })
    assert resp.status_code == 302

    dv.refresh_from_db()
    assert dv.status == "rejected"
    assert dv.verifier == recruiter_user
    assert dv.comments == "Blurry scan."

    # Legacy flag stays False
    doc.refresh_from_db()
    assert doc.is_verified is False

    # Audit event
    audit = AuditEvent.objects.filter(
        application=application,
        field_name="document_verification",
    ).first()
    assert audit is not None
    assert audit.new_value == "rejected"


def test_viewer_cannot_verify(tenant, application, viewer_user):
    """Viewer role cannot access verify_documents (requires recruiter/hr_manager)."""
    doc = Document.objects.create(
        application=application,
        doc_type="degree",
        file="documents/degree.pdf",
    )
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(viewer_user)
    resp = client.get("/verify-documents/")
    assert resp.status_code == 403


def test_verify_documents_filter_by_status(tenant, application, recruiter_user):
    """Status filter works correctly."""
    doc1 = Document.objects.create(
        application=application,
        doc_type="degree",
        file="documents/d1.pdf",
    )
    doc2 = Document.objects.create(
        application=application,
        doc_type="marksheet",
        file="documents/d2.pdf",
    )
    doc2.verification.status = "verified"
    doc2.verification.save()

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(recruiter_user)

    # Filter pending
    resp = client.get("/verify-documents/?status=pending")
    content = resp.content.decode()
    assert "degree" in content
    assert "marksheet" not in content or content.count("marksheet") == 0

    # Filter all
    resp = client.get("/verify-documents/?status=all")
    content = resp.content.decode()
    assert content.count("degree") >= 1


def test_document_verification_dashboard_view(tenant, application, recruiter_user):
    """Dashboard shows verification summary."""
    doc = Document.objects.create(
        application=application,
        doc_type="degree",
        file="documents/degree.pdf",
    )
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(recruiter_user)
    resp = client.get("/document-verification/dashboard/")
    assert resp.status_code == 200
    content = resp.content.decode()
    assert "Document Verification Dashboard" in content
    assert "Pending" in content


def test_hr_manager_can_verify(tenant, application, staff_user):
    """hr_manager role can also verify documents."""
    doc = Document.objects.create(
        application=application,
        doc_type="degree",
        file="documents/degree.pdf",
    )
    dv = doc.verification

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    resp = client.post("/verify-documents/", {
        "verification_id": dv.id,
        "action": "verified",
        "comments": "Approved by HR.",
    })
    assert resp.status_code == 302
    dv.refresh_from_db()
    assert dv.status == "verified"
