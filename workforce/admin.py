from django.contrib import admin
from .models import RetirementForecast, ManpowerRequirement, RecruitmentBatch


@admin.register(RetirementForecast)
class RetirementForecastAdmin(admin.ModelAdmin):
    list_display = ("year", "executives", "supervisors", "workmen", "total")


@admin.register(ManpowerRequirement)
class ManpowerRequirementAdmin(admin.ModelAdmin):
    list_display = ("period_start", "period_end", "executives", "supervisors", "workmen", "total")


@admin.register(RecruitmentBatch)
class RecruitmentBatchAdmin(admin.ModelAdmin):
    list_display = (
        "name", "target_posts", "advertisement_window_start", "advertisement_window_end",
        "expected_joining_start", "is_approved",
    )
    list_filter = ("is_approved",)
