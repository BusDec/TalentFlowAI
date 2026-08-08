from django.contrib import admin
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
