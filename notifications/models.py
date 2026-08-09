"""Notification outbox and template models."""

from django.db import models


class NotificationOutbox(models.Model):
    """Every notification attempt is recorded here (outbox pattern).

    Status flow: queued -> sent | failed
    """

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    CHANNEL_CHOICES = [
        ("sms", "SMS"),
        ("email", "Email"),
        ("portal", "Portal"),
    ]

    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    to = models.CharField(max_length=255, help_text="Recipient (phone, email, or user id)")
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="queued")
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification({self.channel} -> {self.to}, {self.status})"


class NotificationTemplate(models.Model):
    """Reusable notification body templates keyed by name."""

    name = models.CharField(max_length=100, unique=True)
    channel = models.CharField(max_length=20, choices=NotificationOutbox.CHANNEL_CHOICES)
    subject = models.CharField(max_length=255, blank=True)
    body_template = models.TextField(help_text="Body text; use {variable} placeholders.")
    created_at = models.DateTimeField(auto_now_add=True)

    def render(self, **kwargs) -> str:
        """Render the template with the given context variables."""
        return self.body_template.format(**kwargs)

    def __str__(self):
        return self.name
