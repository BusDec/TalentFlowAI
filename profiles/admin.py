from django.contrib import admin

from .models import (
    AcademicRecord,
    CandidateProfile,
    ExamDisclosure,
    ProfileDocument,
    WorkExperience,
)


@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    # Aadhaar is encrypted at rest and must never be shown unmasked in list
    # views; ciphertext also cannot be searched, so search by candidate only.
    list_display = ["candidate", "category", "gender", "display_aadhaar", "updated_at"]
    search_fields = ["candidate__first_name", "candidate__last_name"]


@admin.register(AcademicRecord)
class AcademicRecordAdmin(admin.ModelAdmin):
    list_display = ["candidate", "level", "discipline", "year_passed", "score"]
    search_fields = ["candidate__first_name", "candidate__last_name"]


@admin.register(WorkExperience)
class WorkExperienceAdmin(admin.ModelAdmin):
    list_display = ["candidate", "org_name", "designation", "start_date", "end_date"]


@admin.register(ExamDisclosure)
class ExamDisclosureAdmin(admin.ModelAdmin):
    list_display = ["candidate", "exam_type", "gate_year", "gate_score", "air"]


@admin.register(ProfileDocument)
class ProfileDocumentAdmin(admin.ModelAdmin):
    list_display = ["candidate", "doc_type", "uploaded_at"]
