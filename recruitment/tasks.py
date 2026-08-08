"""Celery tasks for asynchronous document processing (Phase 1.3).

Resume parsing, resume evaluation, and duplicate detection are dispatched
asynchronously from Django signals / views. In development
(CELERY_TASK_ALWAYS_EAGER=True) these run synchronously in-process.
"""

from celery import shared_task
from django.utils import timezone

from agents.duplicate_detection import flag_duplicates
from agents.resume_evaluator import evaluate_resume
from agents.resume_parser import parse_resume
from .models import Application, Resume


@shared_task
def parse_resume_task(resume_id):
    """Parse a resume file, persist the result, then evaluate its applications.

    Never re-raises: a failure marks the resume as failed instead of
    poisoning the broker (or the caller in eager mode).
    """
    resume = Resume.objects.get(id=resume_id)
    resume.parse_status = "processing"
    resume.save(update_fields=["parse_status"])

    try:
        parsed, confidence, method = parse_resume(resume.file.path)
        if method == "ocr_failed" or not parsed:
            resume.parse_status = "failed"
            resume.parsed_json = {}
            resume.parse_error = "OCR/parse failed"
            resume.save(update_fields=["parse_status", "parsed_json", "parse_error"])
        else:
            resume.parsed_json = parsed
            resume.confidence = confidence
            resume.parse_status = "parsed"
            resume.parsed_at = timezone.now()
            resume.save(update_fields=["parsed_json", "confidence", "parse_status", "parsed_at"])
    except Exception as exc:  # noqa: BLE001 - mark failed instead of re-raising
        resume.parse_status = "failed"
        resume.parse_error = str(exc)[:500]
        resume.save(update_fields=["parse_status", "parse_error"])
    finally:
        evaluate_applications_for_resume.delay(resume_id)


@shared_task
def evaluate_applications_for_resume(resume_id):
    """Score every application of the resume's candidate from the parsed data."""
    resume = Resume.objects.filter(id=resume_id).first()
    if resume is None or resume.parsed_json is None:
        return

    for application in resume.candidate.applications.all():
        evaluation = evaluate_resume(resume.parsed_json, application.post)
        application.resume_score = evaluation.get("overall_score", 0)
        application.resume_evaluation = evaluation
        application.save(update_fields=["resume_score", "resume_evaluation"])


@shared_task
def flag_duplicates_task(application_id):
    """Detect and record duplicate applications for human resolution."""
    application = Application.objects.get(id=application_id)
    created = flag_duplicates(application)
    return len(created)
