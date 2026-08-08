"""Consent management — DPDP-compliant consent ledger (per-tenant schema)."""

from django.db import models
from django.conf import settings
from django.utils import timezone


class Consent(models.Model):
    """Explicit, purpose-limited consent granted by a candidate."""

    PURPOSE_CHOICES = (
        ("application", "Application Processing"),
        ("digilocker", "DigiLocker Document Fetch"),
        ("interview", "Interview Recording"),
        ("background_check", "Background Verification"),
        ("resume_parsing", "Resume Parsing"),
        ("data_retention", "Data Retention"),
    )

    candidate_portal_user = models.ForeignKey(
        "portal.CandidatePortalUser",
        on_delete=models.CASCADE,
        related_name="consents",
    )
    application = models.ForeignKey(
        "recruitment.Application",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consents",
        help_text="The application/post this consent is linked to, if any.",
    )
    purpose = models.CharField(max_length=40, choices=PURPOSE_CHOICES)
    scope_text = models.TextField(blank=True, help_text="Plain-language description of what data is used and why.")
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ["-granted_at"]

    @property
    def is_active(self):
        now = timezone.now()
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)

    def __str__(self):
        return f"{self.candidate_portal_user} — {self.get_purpose_display()}"


class ConsentEvent(models.Model):
    """Immutable audit trail of every consent lifecycle action."""

    ACTION_CHOICES = (
        ("granted", "Granted"),
        ("revoked", "Revoked"),
        ("expired", "Expired"),
        ("viewed", "Viewed"),
        ("updated", "Updated"),
    )

    consent = models.ForeignKey(Consent, on_delete=models.CASCADE, related_name="events")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Human actor, if any. System actions have None.",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    details = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]
        verbose_name = "Consent Event"

    def __str__(self):
        return f"{self.consent_id} — {self.action} @ {self.timestamp:%Y-%m-%d %H:%M}"
