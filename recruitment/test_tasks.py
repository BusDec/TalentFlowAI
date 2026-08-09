"""Tests for async document processing tasks (Phase 1.3).

Runs with CELERY_TASK_ALWAYS_EAGER=True (dev default), so .delay() executes
synchronously and returns an AsyncResult (EagerResult) that is .successful().
"""

from celery.result import AsyncResult
from django.core.files.uploadedfile import SimpleUploadedFile

from recruitment.models import Application, Candidate, DuplicateFlag, Resume
from recruitment.tasks import (
    evaluate_applications_for_resume,
    flag_duplicates_task,
    parse_resume_task,
)


def _make_resume(application, content=b"Resume text for parsing", name="resume.txt"):
    """Create a Resume for the application's candidate via the ORM."""
    return Resume.objects.create(
        candidate=application.candidate,
        file=SimpleUploadedFile(name, content, content_type="text/plain"),
    )


def test_resume_task_transitions(application):
    resume = _make_resume(application)

    result = parse_resume_task.delay(resume.id)

    # In eager mode .delay() returns an AsyncResult that completed successfully.
    assert isinstance(result, AsyncResult)
    assert result.successful() is True

    resume.refresh_from_db()
    assert resume.parse_status in ("parsed", "failed")
    if resume.parse_status == "parsed":
        assert isinstance(resume.parsed_json, dict)
        assert resume.confidence > 0
    else:
        assert resume.parse_error


def test_evaluate_task_scores_application(application):
    resume = _make_resume(application)
    # Fabricate parsed data (the eager parse signal may have marked it failed).
    resume.parsed_json = {"skills": ["python"]}
    resume.parse_status = "parsed"
    resume.save(update_fields=["parsed_json", "parse_status"])

    evaluate_applications_for_resume.delay(resume.id)

    application.refresh_from_db()
    assert isinstance(application.resume_score, int)
    assert application.resume_score >= 0
    assert isinstance(application.resume_evaluation, dict)


def test_flag_duplicates_task_creates_flag(application, advertisement):
    first_candidate = application.candidate
    second_candidate = Candidate.objects.create(
        first_name=first_candidate.first_name,
        last_name=first_candidate.last_name,
        email=first_candidate.email,
        mobile=first_candidate.mobile,
        date_of_birth=first_candidate.date_of_birth,
    )
    second_app = Application.objects.create(
        post=advertisement.posts.last(),
        candidate=second_candidate,
        application_id="TF20260002",
        status="received",
    )

    # The Application post_save signal already flagged this eagerly; clear so we
    # exercise the task itself.
    DuplicateFlag.objects.all().delete()

    result = flag_duplicates_task.delay(second_app.id)
    assert result.successful() is True
    assert DuplicateFlag.objects.filter(application_a=second_app).count() >= 1


def test_signal_dispatches_task(application):
    resume = _make_resume(application)

    # post_save dispatched parse_resume_task eagerly; status must have moved off "pending".
    resume.refresh_from_db()
    assert resume.parse_status != "pending"


def test_parse_document_task_populates_extracted_data(tenant, application):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from recruitment.models import Document
    from recruitment.tasks import parse_document_task
    doc = Document.objects.create(
        application=application, doc_type="certificate:GATE scorecard",
        file=SimpleUploadedFile("gate.txt", b"GATE scorecard\nABCDE1234F\nName: R K", content_type="text/plain"),
    )
    parse_document_task.delay(doc.id)
    doc.refresh_from_db()
    assert isinstance(doc.extracted_data, dict)
    assert "doc_type" in doc.extracted_data
