"""Recruitment core models — Phase I (per-tenant schema)."""

from django.conf import settings
from django.db import models


class Advertisement(models.Model):
    """A public recruitment notification (e.g. NEEPCO/02/2026)."""

    title = models.CharField(max_length=255)
    advt_number = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    published_date = models.DateField()
    closing_date = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Boilerplate sections (pre-filled with standard NEEPCO text)
    health_text = models.TextField(blank=True)
    general_conditions = models.TextField(blank=True)
    how_to_apply = models.TextField(blank=True)

    class Meta:
        ordering = ["-published_date"]

    def __str__(self):
        return f"{self.advt_number} - {self.title}"


class Post(models.Model):
    """A post (vacancy type) within an advertisement."""

    advertisement = models.ForeignKey(Advertisement, on_delete=models.CASCADE, related_name="posts")
    name = models.CharField(max_length=200)
    post_code = models.CharField(max_length=50)
    vacancies = models.PositiveIntegerField(default=1)
    max_age = models.PositiveIntegerField(null=True, blank=True)
    qualification = models.TextField()
    experience_required = models.TextField(blank=True)
    pay_scale = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=300, blank=True, default="Shillong or any Offices/Project sites of NEEPCO, anywhere in India")
    period_of_engagement = models.CharField(max_length=300, blank=True, default="Initially for 3 (three) years and extendable by further 2 (two) years on yearly basis based on the performance and requirement")
    category_breakup = models.JSONField(default=dict, blank=True, help_text="e.g. {'ur': 2, 'ews': 0, 'obc': 1, 'sc': 0, 'st': 0}")
    required_certificates = models.JSONField(
        default=list,
        blank=True,
        help_text="Certificates applicants must upload (e.g. SAP, Primavera, GATE scorecard).",
    )
    EDUCATION_LEVEL_CHOICES = (
        ("x", "Class X"),
        ("xii", "Class XII"),
        ("diploma", "Diploma"),
        ("graduate", "Graduate"),
        ("pg", "Post Graduate"),
        ("phd", "PhD"),
    )
    min_education_level = models.CharField(
        max_length=20,
        choices=EDUCATION_LEVEL_CHOICES,
        blank=True,
        help_text="Minimum education level required for the post.",
    )
    min_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum aggregate percentage required (e.g. 60.00).",
    )
    experience_years = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum years of relevant experience required.",
    )
    age_cutoff_date = models.DateField(
        null=True,
        blank=True,
        help_text="Reference date against which age limits are computed (e.g. advertisement closing date).",
    )

    class Meta:
        ordering = ["name"]
        unique_together = ("advertisement", "post_code")

    @property
    def category_breakup_display(self):
        if not self.category_breakup:
            return ""
        parts = []
        for key, val in self.category_breakup.items():
            if val:
                parts.append(f"{key.upper()}-{val}")
        return ", ".join(parts) if parts else ""

    def __str__(self):
        return f"{self.name} ({self.post_code})"


class Candidate(models.Model):
    """A person who has applied. One portal user may map to many candidates."""

    portal_user = models.ForeignKey(
        "portal.CandidatePortalUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="candidates",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    mobile = models.CharField(max_length=15, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Application(models.Model):
    """A single application from a candidate against a post."""

    STATUS_CHOICES = (
        ("received", "Received"),
        ("document_verification", "Document Verification"),
        ("shortlisted", "Shortlisted"),
        ("interview", "Interview"),
        ("offered", "Offered"),
        ("joined", "Joined"),
        ("rejected", "Rejected"),
        ("withdrawn", "Withdrawn"),
    )

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="applications")
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="applications")
    application_id = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="received")
    rejected_at_stage = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        blank=True,
        null=True,
        help_text="Stage at which the application was rejected/withdrawn (shown as a red X in the candidate stepper).",
    )
    applied_at = models.DateTimeField(auto_now_add=True)
    employee_number = models.CharField(max_length=50, blank=True, null=True)
    resume_score = models.PositiveSmallIntegerField(default=0, help_text="AI-evaluated resume score 0-100.")
    resume_evaluation = models.JSONField(
        null=True, blank=True, help_text="Detailed competency matrix from Resume Evaluator Agent."
    )
    evaluation_notes = models.TextField(blank=True, help_text="Human notes on the AI evaluation.")

    class Meta:
        ordering = ["-applied_at"]
        unique_together = ("post", "candidate")

    def save(self, *args, **kwargs):
        import re
        if self.application_id:
            self.application_id = re.sub(r"[^A-Za-z0-9_-]", "", self.application_id)

        previous = None
        if self.pk:
            try:
                previous = Application.objects.only("status", "resume_score").get(pk=self.pk)
            except Application.DoesNotExist:
                previous = None

        actor = kwargs.pop("audit_actor", None)
        update_fields = kwargs.get("update_fields")

        super().save(*args, **kwargs)

        if previous is not None:
            from .audit import log_audit
            # Respect update_fields: only audit fields that were actually written.
            status_written = update_fields is None or "status" in update_fields
            score_written = update_fields is None or "resume_score" in update_fields
            if status_written and previous.status != self.status:
                log_audit(actor, self, "status", previous.status, self.status)
            if score_written and previous.resume_score != self.resume_score:
                log_audit(actor, self, "resume_score", previous.resume_score, self.resume_score)

    def __str__(self):
        return self.application_id


class Document(models.Model):
    """A candidate-submitted document linked to an application."""

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=50)  # degree, dob, experience, category_certificate...
    file = models.FileField(upload_to="documents/")
    extracted_data = models.JSONField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.doc_type} - {self.application.application_id}"


class FetchedDocument(models.Model):
    """Document pulled from DigiLocker / NAD (college) — consent-gated."""

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="fetched_documents")
    doc_type = models.CharField(max_length=50)  # aadhaar, degree, marksheet, experience...
    issuer = models.CharField(max_length=200, blank=True)
    issue_date = models.CharField(max_length=30, blank=True)
    data = models.JSONField(default=dict, blank=True)
    signature_valid = models.BooleanField(default=False)
    source = models.CharField(max_length=20, default="digilocker")
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fetched_at"]

    def __str__(self):
        return f"{self.source}:{self.doc_type} - {self.application.application_id}"


class BackgroundReport(models.Model):
    """Neutral tabulated background facts compiled for candidate explanation + human review."""

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("explained", "Candidate Explained"),
        ("reviewed", "Reviewed"),
    )

    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name="background_report")
    facts = models.JSONField(default=dict, blank=True)
    candidate_explanation = models.TextField(blank=True)
    reviewer_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    generated_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    def __str__(self):
        return f"BG Report - {self.application.application_id}"


class Resume(models.Model):
    """Candidate resume; parsed JSON reused across multiple applications."""

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="resumes")
    file = models.FileField(upload_to="resumes/")
    parsed_json = models.JSONField(null=True, blank=True)
    confidence = models.DecimalField(max_digits=4, decimal_places=2, default=0.0)
    parse_status = models.CharField(
        max_length=20,
        choices=(("pending", "Pending"), ("parsed", "Parsed"), ("failed", "Failed")),
        default="pending",
    )
    parsed_at = models.DateTimeField(null=True, blank=True)
    parse_error = models.TextField(blank=True, help_text="Parsing error message when parse_status='failed'.")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Resume - {self.candidate}"


class RosterMatrix(models.Model):
    """Category-wise vacancy matrix for a post (vertical + PwBD horizontal)."""

    CATEGORY_CHOICES = (
        ("ur", "UR"),
        ("obc", "OBC (NCL)"),
        ("sc", "SC"),
        ("st", "ST"),
        ("ews", "EWS"),
    )

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="roster_matrix")
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    vertical_vacancies = models.PositiveIntegerField(default=0)
    pwbd_horizontal_vacancies = models.PositiveIntegerField(default=0)
    carry_forward = models.BooleanField(default=False, help_text="Unfilled backlog to carry forward.")

    class Meta:
        ordering = ["post", "category"]
        unique_together = ("post", "category")

    @property
    def filled_count(self):
        return CategoryAllocation.objects.filter(
            application__post=self.post,
            category=self.category,
            fills_slot=True,
        ).count()

    @property
    def total_vacancies(self):
        return self.vertical_vacancies + self.pwbd_horizontal_vacancies

    @property
    def is_full(self):
        return self.filled_count >= self.total_vacancies

    @property
    def breach_warning(self):
        """Returns a warning string when overfilled."""
        if self.filled_count > self.total_vacancies:
            return (
                f"ROSTER BREACH: {self.get_category_display()} for {self.post.name} "
                f"filled {self.filled_count}/{self.total_vacancies}."
            )
        return ""

    def __str__(self):
        return f"{self.post} - {self.get_category_display()} ({self.filled_count}/{self.total_vacancies})"


class CategoryAllocation(models.Model):
    """Category claimed/verified for an application, tied to roster slot."""

    CATEGORY_CHOICES = RosterMatrix.CATEGORY_CHOICES + (("pwbd", "PwBD"),)

    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="category_allocations"
    )
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    certificate_file = models.FileField(upload_to="category_certificates/", blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    fills_slot = models.BooleanField(default=False, help_text="Set True at offer time to consume a roster slot.")
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("application", "category")

    def __str__(self):
        return f"{self.application.application_id} - {self.get_category_display()}"


class PanelList(models.Model):
    """Ranked list of successful candidates beyond advertised vacancies."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="panel_list")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="panel_entry")
    panel_rank = models.PositiveIntegerField()
    valid_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    promoted_on = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["post", "panel_rank"]
        unique_together = ("post", "application")

    def __str__(self):
        return f"{self.post} - {self.panel_rank}. {self.application}"


class InternalJobPosting(models.Model):
    """Internal-only vacancy for existing employees."""

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    grade = models.CharField(max_length=50, blank=True)
    min_experience_years = models.PositiveIntegerField(default=0)
    deputation_eligible = models.BooleanField(default=False)
    open_from = models.DateField()
    open_until = models.DateField()
    priority_flag = models.CharField(
        max_length=20,
        choices=(("normal", "Normal"), ("high", "High"), ("critical", "Critical")),
        default="normal",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class InternalApplication(models.Model):
    """Employee application against an internal posting."""

    STATUS_CHOICES = (
        ("applied", "Applied"),
        ("shortlisted", "Shortlisted"),
        ("selected", "Selected"),
        ("rejected", "Rejected"),
    )

    posting = models.ForeignKey(InternalJobPosting, on_delete=models.CASCADE, related_name="applications")
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="internal_applications")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="applied")
    current_grade = models.CharField(max_length=50, blank=True)
    years_at_org = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("posting", "applicant")

    def __str__(self):
        return f"{self.applicant} -> {self.posting}"


class DuplicateFlag(models.Model):
    """Cross-advertisement duplicate application detection record."""

    RESOLUTION_CHOICES = (
        ("pending", "Pending"),
        ("genuine_duplicate", "Genuine Duplicate"),
        ("false_positive", "False Positive"),
        ("merged", "Merged"),
    )

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="duplicate_flags")
    application_a = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="+")
    application_b = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="+")
    confidence = models.PositiveSmallIntegerField(default=0, help_text="0-100 match confidence.")
    match_fields = models.JSONField(default=list, blank=True)
    resolution = models.CharField(max_length=30, choices=RESOLUTION_CHOICES, default="pending")
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Duplicate {self.confidence}%: {self.application_a} vs {self.application_b}"


class CommunicationLog(models.Model):
    """Communication hub — records messages sent to candidates at each stage."""

    CHANNEL_CHOICES = (
        ("email", "Email"),
        ("sms", "SMS"),
        ("portal", "Portal Notification"),
    )
    TYPE_CHOICES = (
        ("acknowledgement", "Application Acknowledgement"),
        ("status_update", "Status Update"),
        ("interview_invite", "Interview Invite"),
        ("offer", "Offer Letter"),
        ("rejection", "Rejection"),
    )

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="communications")
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default="portal")
    comm_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.comm_type} -> {self.application.application_id}"


class AuditEvent(models.Model):
    """Immutable record of who changed what on an application and when.

    Written by recruitment.audit.log_audit(). Rows are never updated or
    deleted through the admin — audit trails must survive for RTI requests.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    tenant_schema = models.CharField(
        max_length=63,
        blank=True,
        default="",
        help_text="Tenant schema in which the change happened (schema == tenant identity).",
    )
    application = models.ForeignKey(
        "Application",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["application", "-timestamp"])]
        verbose_name = "Audit Event"

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.field_name} on {self.application}"


class OrgProfile(models.Model):
    """Single per-tenant organisation identity row (schema == tenant)."""

    name_en = models.CharField(max_length=200)
    name_hi = models.CharField(max_length=200, blank=True)
    tagline_en = models.CharField(max_length=200, blank=True)
    tagline_hi = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    footer_motto = models.CharField(max_length=300, blank=True)
    contact_email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    sbi_epay_text = models.TextField(
        blank=True,
        help_text="Registration fee / SBI ePay payment instructions (moved from Advertisement.registration_fee_text).",
    )
    logo = models.ImageField(upload_to="org_logos/", blank=True, null=True)
    accent_color = models.CharField(
        max_length=9,
        default="#0b3d91",
        help_text="CSS hex color (e.g. #0b3d91) used for portal accent theming.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organisation Profile"
        constraints = [
            # Enforce a single profile row per schema: a partial unique index
            # on the constant 1 allows at most one real row (pk IS NOT NULL
            # excludes the NULL-pk placeholder Django uses during checks).
            models.UniqueConstraint(
                models.Value(1),
                condition=models.Q(pk__isnull=False),
                name="orgprofile_singleton_row",
            )
        ]

    def __str__(self):
        return self.name_en


class EligibilityOverride(models.Model):
    """Manual override of the automated eligibility verdict for an application.

    One optional override per application: when present, its verdict takes
    precedence over the Eligibility Engine's computed result.
    """

    application = models.OneToOneField(
        Application,
        on_delete=models.CASCADE,
        related_name="eligibility_override",
    )
    verdict = models.BooleanField(help_text="Final eligibility verdict after human review (True = eligible).")
    reason = models.TextField(help_text="Justification recorded by the overrider.")
    overridden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="User who recorded the override.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Eligibility Override"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Override {self.application.application_id}: {self.verdict}"


class PostBasedRoster(models.Model):
    """DoPT 100-point roster for a post, persisted once generated.

    ``roster_points`` holds the ordered list of roster entries
    (``{"serial", "category", "point_type"}``) produced by
    ``recruitment.roster.build_roster``.  ``current_position`` tracks the next
    serial to fill as candidates are appointed; ``liaison_officer`` and
    ``certified_by`` record human accountability for the cycle.
    """

    post = models.OneToOneField(
        Post,
        on_delete=models.CASCADE,
        related_name="roster",
        help_text="Post this roster cycle belongs to.",
    )
    cycle_start_year = models.PositiveIntegerField(
        help_text="Calendar year in which this roster cycle began."
    )
    roster_points = models.JSONField(
        default=list,
        help_text="Ordered 100-point roster: [{'serial', 'category', 'point_type'}, ...].",
    )
    current_position = models.PositiveIntegerField(
        default=1, help_text="Next serial in the roster to be filled."
    )
    liaison_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="roster_liaison_for",
        help_text="Officer responsible for maintaining this roster.",
    )
    certified_on = models.DateTimeField(
        null=True, blank=True, help_text="When the roster was last certified."
    )
    certified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="roster_certified",
        help_text="User who certified the roster cycle.",
    )

    class Meta:
        verbose_name = "Post Based Roster"
        ordering = ["-cycle_start_year"]

    def __str__(self):
        return f"{self.post} roster ({self.cycle_start_year})"
