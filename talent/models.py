"""Talent intelligence models — Phase III foundation (per-tenant schema)."""

from django.conf import settings
from django.db import models


class Skill(models.Model):
    """A named skill/competency."""

    name = models.CharField(max_length=150, unique=True)
    category = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.name


class EmployeeSkill(models.Model):
    """Skill proficiency for an employee."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="skills")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    proficiency = models.DecimalField(max_digits=3, decimal_places=1, default=1.0)
    verified = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "skill")

    def __str__(self):
        return f"{self.user} - {self.skill} ({self.proficiency})"


class TrainingNeed(models.Model):
    """A diagnosed training requirement (from TNA Agent)."""

    PRIORITY_CHOICES = (
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="medium")
    target_count = models.PositiveIntegerField(default=0)
    recommended_timeline = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
