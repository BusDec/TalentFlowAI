"""Workforce planning model test foundation."""

from workforce.models import ManpowerRequirement, RecruitmentBatch, RetirementForecast


def test_retirement_forecast(tenant):
    """Year-wise separation forecasts persist with headcount buckets."""
    forecast = RetirementForecast.objects.create(
        year=2030, executives=5, supervisors=10, workmen=20, total=35
    )
    forecast.refresh_from_db()
    assert str(forecast) == "Retirement Forecast 2030"
    assert forecast.year == 2030
    assert forecast.executives == 5
    assert forecast.supervisors == 10
    assert forecast.workmen == 20
    assert forecast.total == 35


def test_manpower_requirement(tenant):
    """Net manpower demand persists across a planning period."""
    requirement = ManpowerRequirement.objects.create(
        period_start="2026-04-01",
        period_end="2027-03-31",
        executives=2,
        supervisors=4,
        workmen=6,
        total=12,
        primary_drivers="New hydro project",
    )
    requirement.refresh_from_db()
    assert str(requirement).startswith("Requirement 2026-04-01")
    assert requirement.executives == 2
    assert requirement.total == 12
    assert requirement.primary_drivers == "New hydro project"


def test_recruitment_batch(tenant):
    """Recruitment calendar batches persist with their windows."""
    batch = RecruitmentBatch.objects.create(
        name="Batch 2026-01",
        advertisement_window_start="2026-04-01",
        advertisement_window_end="2026-05-15",
        target_posts=3,
        expected_joining_start="2026-08-01",
        expected_joining_end="2026-09-30",
        purpose="Annual recruitment drive",
    )
    batch.refresh_from_db()
    assert str(batch) == "Batch 2026-01"
    assert batch.target_posts == 3
    assert batch.is_approved is False
    assert batch.purpose == "Annual recruitment drive"
