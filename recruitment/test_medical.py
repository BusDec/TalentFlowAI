"""Tests for MedicalExam — medical examination scheduling, report upload, and fitness certification."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import Client

from conftest import TENANT_DOMAIN, make_staff_user
from recruitment.models import AuditEvent, MedicalExam

User = get_user_model()


# ── Model tests ─────────────────────────────────────────────────────────────


def test_medical_exam_create(tenant, application):
    """MedicalExam can be created with all required fields."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="AIIMS Guwahati",
        exam_date=date.today() + timedelta(days=7),
    )
    assert exam.pk is not None
    assert exam.application == application
    assert exam.hospital == "AIIMS Guwahati"
    assert exam.fitness_status == "pending"
    assert exam.report_file.name == ""
    assert exam.notes == ""
    assert exam.created_at is not None
    assert exam.updated_at is not None


def test_medical_exam_str(tenant, application):
    """__str__ shows application_id and fitness status."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="GMCH",
        exam_date=date.today(),
    )
    s = str(exam)
    assert application.application_id in s
    assert "Pending" in s


def test_medical_exam_str_fit(tenant, application):
    """__str__ shows 'Fit' when fitness_status is fit."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="GMCH",
        exam_date=date.today(),
        fitness_status="fit",
    )
    s = str(exam)
    assert "Fit" in s


def test_medical_exam_str_unfit(tenant, application):
    """__str__ shows 'Unfit' when fitness_status is unfit."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="GMCH",
        exam_date=date.today(),
        fitness_status="unfit",
    )
    s = str(exam)
    assert "Unfit" in s


def test_medical_exam_fitness_status_default(tenant, application):
    """Default fitness_status is 'pending'."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="Test Hospital",
        exam_date=date.today(),
    )
    exam.refresh_from_db()
    assert exam.fitness_status == "pending"


def test_medical_exam_notes_optional(tenant, application):
    """Notes field is optional and defaults to blank."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="Test Hospital",
        exam_date=date.today(),
    )
    assert exam.notes == ""


def test_medical_exam_application_relationship(tenant, application):
    """Application can access its medical_exams reverse relation."""
    MedicalExam.objects.create(
        application=application,
        hospital="Hospital A",
        exam_date=date.today(),
    )
    MedicalExam.objects.create(
        application=application,
        hospital="Hospital B",
        exam_date=date.today(),
    )
    assert application.medical_exams.count() == 2


# ── View tests ──────────────────────────────────────────────────────────────


def test_medical_schedule_view_get(tenant, application, staff_user):
    """HR manager can view the schedule medical exam form."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.get(f"/applications/{application.application_id}/medical/schedule/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Schedule" in content
    assert "Hospital" in content


def test_medical_schedule_view_post(tenant, application, staff_user):
    """HR manager can schedule a medical exam via POST."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    exam_date = (date.today() + timedelta(days=14)).isoformat()
    response = client.post(
        f"/applications/{application.application_id}/medical/schedule/",
        data={
            "hospital": "NEIGRIHMS Shillong",
            "exam_date": exam_date,
            "notes": "Bring original certificates",
        },
    )
    assert response.status_code == 302
    exam = MedicalExam.objects.filter(application=application).first()
    assert exam is not None
    assert exam.hospital == "NEIGRIHMS Shillong"
    assert str(exam.exam_date) == exam_date
    assert exam.notes == "Bring original certificates"


def test_medical_schedule_view_post_missing_fields(tenant, application, staff_user):
    """POST with missing hospital or exam_date shows error."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.post(
        f"/applications/{application.application_id}/medical/schedule/",
        data={"hospital": "", "exam_date": ""},
    )
    assert response.status_code == 200  # re-renders form
    assert MedicalExam.objects.filter(application=application).count() == 0


def test_medical_upload_report_view(tenant, application, staff_user, recruiter_user):
    """Recruiter can upload a medical report file via POST."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="AIIMS",
        exam_date=date.today(),
    )

    from django.core.files.uploadedfile import SimpleUploadedFile

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(recruiter_user)
    report_file = SimpleUploadedFile(
        "medical_report.pdf",
        b"%PDF-1.4 test content",
        content_type="application/pdf",
    )
    response = client.post(
        f"/medical/{exam.pk}/upload-report/",
        data={"report_file": report_file, "notes": "All clear"},
    )
    assert response.status_code == 302
    exam.refresh_from_db()
    assert exam.report_file.name != ""
    assert "All clear" in exam.notes


def test_medical_upload_report_view_no_file(tenant, application, recruiter_user):
    """POST without a file shows error."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="AIIMS",
        exam_date=date.today(),
    )

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(recruiter_user)
    response = client.post(f"/medical/{exam.pk}/upload-report/", data={})
    assert response.status_code == 302  # redirect with error message
    exam.refresh_from_db()
    assert exam.report_file.name == ""


def test_medical_certify_fit(tenant, application, staff_user):
    """HR manager can certify fitness as 'fit'. Creates audit event."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="AIIMS",
        exam_date=date.today(),
    )

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.post(
        f"/medical/{exam.pk}/certify/",
        data={"fitness_status": "fit", "notes": "All parameters normal"},
    )
    assert response.status_code == 302
    exam.refresh_from_db()
    assert exam.fitness_status == "fit"
    assert "All parameters normal" in exam.notes

    # Audit event created
    event = AuditEvent.objects.filter(
        application=application,
        field_name="medical_fitness",
    ).first()
    assert event is not None
    assert event.old_value == "pending"
    assert event.new_value == "fit"


def test_medical_certify_unfit(tenant, application, staff_user):
    """HR manager can certify fitness as 'unfit'. Creates audit event."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="GMCH",
        exam_date=date.today(),
        fitness_status="pending",
    )

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.post(
        f"/medical/{exam.pk}/certify/",
        data={"fitness_status": "unfit", "notes": "Blood pressure above threshold"},
    )
    assert response.status_code == 302
    exam.refresh_from_db()
    assert exam.fitness_status == "unfit"

    event = AuditEvent.objects.filter(
        application=application,
        field_name="medical_fitness",
    ).first()
    assert event is not None
    assert event.old_value == "pending"
    assert event.new_value == "unfit"


def test_medical_certify_invalid_status(tenant, application, staff_user):
    """POST with invalid fitness_status is rejected."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="AIIMS",
        exam_date=date.today(),
    )

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.post(
        f"/medical/{exam.pk}/certify/",
        data={"fitness_status": "invalid_value"},
    )
    assert response.status_code == 302
    exam.refresh_from_db()
    assert exam.fitness_status == "pending"  # unchanged


def test_medical_certify_no_audit_on_same_status(tenant, application, staff_user):
    """No audit event when status doesn't actually change."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="AIIMS",
        exam_date=date.today(),
        fitness_status="fit",
    )

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    client.post(
        f"/medical/{exam.pk}/certify/",
        data={"fitness_status": "fit"},
    )

    events = AuditEvent.objects.filter(
        application=application,
        field_name="medical_fitness",
    )
    assert events.count() == 0


# ── Role access tests ──────────────────────────────────────────────────────


def test_medical_schedule_requires_hr_manager(tenant, application, recruiter_user):
    """Recruiter cannot access the schedule view (requires hr_manager)."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(recruiter_user)
    response = client.get(f"/applications/{application.application_id}/medical/schedule/")
    # Non-hr_manager gets 403 or redirected depending on decorator implementation
    assert response.status_code in (302, 403)


def test_medical_certify_requires_hr_manager(tenant, application, recruiter_user):
    """Recruiter cannot certify fitness (requires hr_manager)."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="AIIMS",
        exam_date=date.today(),
    )

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(recruiter_user)
    response = client.post(
        f"/medical/{exam.pk}/certify/",
        data={"fitness_status": "fit"},
    )
    assert response.status_code in (302, 403)
    exam.refresh_from_db()
    assert exam.fitness_status == "pending"


def test_medical_upload_requires_recruiter(tenant, application, staff_user):
    """HR manager cannot upload report (requires recruiter)."""
    exam = MedicalExam.objects.create(
        application=application,
        hospital="AIIMS",
        exam_date=date.today(),
    )

    from django.core.files.uploadedfile import SimpleUploadedFile

    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    report_file = SimpleUploadedFile("report.pdf", b"test", content_type="application/pdf")
    response = client.post(
        f"/medical/{exam.pk}/upload-report/",
        data={"report_file": report_file},
    )
    assert response.status_code in (302, 403)
    exam.refresh_from_db()
    assert exam.report_file.name == ""
