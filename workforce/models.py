"""Workforce planning models — Phase II (per-tenant schema)."""

from django.db import models


class RetirementForecast(models.Model):
    """Year-wise projected superannuation + attrition separations."""

    year = models.PositiveIntegerField()
    executives = models.PositiveIntegerField(default=0)
    supervisors = models.PositiveIntegerField(default=0)
    workmen = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["year"]

    def __str__(self):
        return f"Retirement Forecast {self.year}"


class ManpowerRequirement(models.Model):
    """Net manpower demand for a period, driven by projects + separations."""

    period_start = models.DateField()
    period_end = models.DateField()
    executives = models.PositiveIntegerField(default=0)
    supervisors = models.PositiveIntegerField(default=0)
    workmen = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    primary_drivers = models.TextField(blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["period_start"]

    def __str__(self):
        return f"Requirement {self.period_start} to {self.period_end}"


class RecruitmentBatch(models.Model):
    """Lead-time aware recruitment calendar batch (from Workforce Planning Agent)."""

    name = models.CharField(max_length=100)
    advertisement_window_start = models.DateField()
    advertisement_window_end = models.DateField()
    target_posts = models.PositiveIntegerField()
    expected_joining_start = models.DateField()
    expected_joining_end = models.DateField()
    purpose = models.TextField()
    is_approved = models.BooleanField(default=False)

    class Meta:
        ordering = ["advertisement_window_start"]

    def __str__(self):
        return self.name
