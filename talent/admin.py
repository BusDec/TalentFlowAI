from django.contrib import admin
from .models import Skill, EmployeeSkill, TrainingNeed


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name", "category")
    search_fields = ("name",)


@admin.register(EmployeeSkill)
class EmployeeSkillAdmin(admin.ModelAdmin):
    list_display = ("user", "skill", "proficiency", "verified")
    list_filter = ("verified", "skill__category")


@admin.register(TrainingNeed)
class TrainingNeedAdmin(admin.ModelAdmin):
    list_display = ("title", "priority", "target_count", "recommended_timeline")
    list_filter = ("priority",)
