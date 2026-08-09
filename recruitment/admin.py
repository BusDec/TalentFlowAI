import re

from django import forms
from django.contrib import admin
from django.utils.html import escape, mark_safe
from .models import (
    Advertisement,
    Post,
    Candidate,
    Application,
    Document,
    BackgroundReport,
    Resume,
    RosterMatrix,
    CategoryAllocation,
    PanelList,
    InternalJobPosting,
    InternalApplication,
    DuplicateFlag,
    CommunicationLog,
    AuditEvent,
    Grievance,
    MedicalExam,
    OrgProfile,
    JoiningReport,
    PoliceVerification,
    ProbationRecord,
)


class PostInline(admin.TabularInline):
    model = Post
    extra = 0


@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display = ("advt_number", "title", "published_date", "closing_date", "is_active")
    list_filter = ("is_active",)
    search_fields = ("advt_number", "title")
    inlines = [PostInline]


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("name", "post_code", "advertisement", "vacancies", "max_age")
    list_filter = ("advertisement",)


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 0


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "mobile", "date_of_birth", "created_at")
    search_fields = ("first_name", "last_name", "email")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "application_id", "candidate", "post", "status", "applied_at", "employee_number"
    )
    list_filter = ("status", "post__advertisement")
    search_fields = ("application_id", "candidate__email", "employee_number")
    inlines = [DocumentInline]


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("application", "doc_type", "is_verified", "verified_at")
    list_filter = ("doc_type", "is_verified")


@admin.register(BackgroundReport)
class BackgroundReportAdmin(admin.ModelAdmin):
    list_display = ("application", "status", "generated_at", "reviewed_at")
    list_filter = ("status",)


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ("candidate", "parse_status", "confidence", "parsed_at", "uploaded_at")
    list_filter = ("parse_status",)


@admin.register(RosterMatrix)
class RosterMatrixAdmin(admin.ModelAdmin):
    list_display = (
        "post", "category", "vertical_vacancies", "pwbd_horizontal_vacancies",
        "filled_count", "is_full", "carry_forward",
    )
    list_filter = ("category", "carry_forward")
    search_fields = ("post__name", "post__post_code")


@admin.register(CategoryAllocation)
class CategoryAllocationAdmin(admin.ModelAdmin):
    list_display = ("application", "category", "is_verified", "fills_slot", "verified_by", "verified_at")
    list_filter = ("category", "is_verified", "fills_slot")


@admin.register(PanelList)
class PanelListAdmin(admin.ModelAdmin):
    list_display = ("post", "application", "panel_rank", "valid_until", "is_active", "promoted_on")
    list_filter = ("is_active", "post")


@admin.register(InternalJobPosting)
class InternalJobPostingAdmin(admin.ModelAdmin):
    list_display = ("title", "grade", "deputation_eligible", "priority_flag", "open_from", "open_until", "is_active")
    list_filter = ("priority_flag", "is_active", "deputation_eligible")


@admin.register(InternalApplication)
class InternalApplicationAdmin(admin.ModelAdmin):
    list_display = ("applicant", "posting", "status", "applied_at")
    list_filter = ("status",)


@admin.register(DuplicateFlag)
class DuplicateFlagAdmin(admin.ModelAdmin):
    list_display = (
        "candidate", "application_a", "application_b", "confidence", "resolution", "resolved_at"
    )
    list_filter = ("resolution",)
    search_fields = ("candidate__email",)


@admin.register(CommunicationLog)
class CommunicationLogAdmin(admin.ModelAdmin):
    list_display = ("application", "comm_type", "channel", "subject", "sent_at")
    list_filter = ("comm_type", "channel")
    readonly_fields = ("sent_at",)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "actor", "application", "field_name", "old_value", "new_value", "tenant_schema")
    list_filter = ("field_name", "timestamp")
    search_fields = ("application__application_id", "actor__username", "field_name")
    readonly_fields = [f.name for f in AuditEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class OrgProfileForm(forms.ModelForm):
    class Meta:
        model = OrgProfile
        fields = "__all__"

    def clean_accent_color(self):
        value = (self.cleaned_data.get("accent_color") or "").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise forms.ValidationError("Enter a hex color like #0b3d91.")
        return value


@admin.register(OrgProfile)
class OrgProfileAdmin(admin.ModelAdmin):
    form = OrgProfileForm
    list_display = ["name_en", "tagline_en", "contact_email", "updated_at"]
    fieldsets = (
        ("Branding", {"fields": ("name_en", "name_hi", "tagline_en", "tagline_hi", "logo", "accent_color")}),
        ("Contact", {"fields": ("address", "contact_email", "website", "footer_motto")}),
        ("Payments", {"fields": ("sbi_epay_text",)}),
    )
    readonly_fields = ["logo_preview"]

    def has_add_permission(self, request):
        return False  # singleton — created by get_org_profile()

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Logo preview")
    def logo_preview(self, obj):
        if obj.logo:
            return mark_safe(f'<img src="{escape(obj.logo.url)}" height="48">')
        return "—"


@admin.register(Grievance)
class GrievanceAdmin(admin.ModelAdmin):
    list_display = ("subject", "candidate", "status", "assigned_to", "created_at")
    list_filter = ("status",)
    search_fields = ("subject", "candidate__first_name", "candidate__last_name")
    readonly_fields = ("created_at",)


@admin.register(PoliceVerification)
class PoliceVerificationAdmin(admin.ModelAdmin):
    list_display = ("application", "district", "status", "initiated_by", "created_at")
    list_filter = ("status",)
    search_fields = ("application__application_id", "district")
    readonly_fields = ("created_at",)


@admin.register(ProbationRecord)
class ProbationRecordAdmin(admin.ModelAdmin):
    list_display = ("application", "start_date", "end_date", "confirmed_on", "bond_amount", "created_at")
    list_filter = ("confirmed_on",)
    search_fields = ("application__application_id", "application__candidate__first_name", "application__candidate__last_name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(JoiningReport)
class JoiningReportAdmin(admin.ModelAdmin):
    list_display = ("application", "joining_date", "designation", "reported_to", "documents_submitted", "created_at")
    list_filter = ("documents_submitted",)
    search_fields = ("application__application_id", "application__candidate__first_name", "application__candidate__last_name", "designation", "reported_to")
    readonly_fields = ("created_at",)


@admin.register(MedicalExam)
class MedicalExamAdmin(admin.ModelAdmin):
    list_display = ("application", "hospital", "exam_date", "fitness_status", "created_at")
    list_filter = ("fitness_status",)
    search_fields = ("application__application_id", "application__candidate__first_name", "application__candidate__last_name", "hospital")
    readonly_fields = ("created_at", "updated_at")
