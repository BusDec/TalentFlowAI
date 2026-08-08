"""Signals for recruitment app — automated orchestration of Phase I agents."""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from agents.duplicate_detection import flag_duplicates
from agents.resume_evaluator import evaluate_resume
from .models import Application, BackgroundReport, Resume


@receiver(post_save, sender=Application)
def application_post_save(sender, instance, created, **kwargs):
    if created:
        # Auto-create an empty BackgroundReport for every new application.
        BackgroundReport.objects.get_or_create(application=instance)

        # Fire duplicate detection across all advertisements.
        flag_duplicates(instance)


@receiver(post_save, sender=BackgroundReport)
def background_report_post_save(sender, instance, **kwargs):
    # Stamp review timestamps when a human completes review.
    if instance.status == "reviewed" and not instance.reviewed_at:
        instance.reviewed_at = timezone.now()
        instance.save(update_fields=["reviewed_at"])


@receiver(post_save, sender=Resume)
def resume_post_save(sender, instance, created, **kwargs):
    """Parse a newly uploaded resume, then evaluate it against the candidate's applications."""
    if not created:
        return

    from agents.resume_parser import parse_resume

    parsed, confidence, method = parse_resume(instance.file.path)

    if method == "ocr_failed" or not parsed:
        instance.parse_status = "failed"
        instance.parsed_json = {}
        instance.save(update_fields=["parse_status", "parsed_json"])
        return

    instance.parsed_json = parsed
    instance.confidence = confidence
    instance.parse_status = "parsed"
    instance.parsed_at = timezone.now()
    instance.save(update_fields=["parsed_json", "confidence", "parse_status", "parsed_at"])

    # Evaluate against each application this candidate holds.
    for application in instance.candidate.applications.all():
        evaluation = evaluate_resume(parsed, application.post)
        application.resume_score = evaluation.get("overall_score", 0)
        application.resume_evaluation = evaluation
        application.save(update_fields=["resume_score", "resume_evaluation"])
