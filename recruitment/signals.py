"""Signals for recruitment app — automated orchestration of Phase I agents."""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Application, BackgroundReport, Resume
from .tasks import flag_duplicates_task, parse_resume_task


@receiver(post_save, sender=Application)
def application_post_save(sender, instance, created, **kwargs):
    if created:
        # Auto-create an empty BackgroundReport for every new application.
        BackgroundReport.objects.get_or_create(application=instance)

        # Fire duplicate detection asynchronously across all advertisements.
        flag_duplicates_task.delay(instance.id)


@receiver(post_save, sender=BackgroundReport)
def background_report_post_save(sender, instance, **kwargs):
    # Stamp review timestamps when a human completes review.
    if instance.status == "reviewed" and not instance.reviewed_at:
        instance.reviewed_at = timezone.now()
        instance.save(update_fields=["reviewed_at"])


@receiver(post_save, sender=Resume)
def resume_post_save(sender, instance, created, **kwargs):
    """Parse a newly uploaded resume asynchronously, then evaluate it against the candidate's applications."""
    if not created:
        return

    parse_resume_task.delay(instance.id)
