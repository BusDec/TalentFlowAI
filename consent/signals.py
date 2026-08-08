"""Signals for consent app — immutable audit trail of lifecycle events."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Consent, ConsentEvent


@receiver(post_save, sender=Consent)
def consent_post_save(sender, instance, created, **kwargs):
    if created:
        ConsentEvent.objects.create(
            consent=instance,
            action="granted",
            ip_address=instance.ip_address,
            details="Consent record created.",
        )
