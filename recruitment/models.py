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


class Payment(models.Model):
    """Payment record for an application fee.

    Links one-to-one with an ``Application``.  ``exempt`` and ``exempt_reason``
    record whether the candidate was excused from the fee (e.g. SC/ST/OBC/EWS,
    female, PwBD).  ``status`` tracks the payment lifecycle:
    ``pending`` → ``completed`` / ``failed``.
    """

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    )

    application = models.OneToOneField(
        Application,
        on_delete=models.CASCADE,
        related_name="payment",
        help_text="Application this payment is for.",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Fee amount in INR.",
    )
    gateway = models.CharField(
        max_length=50,
        help_text="Payment gateway used (e.g. mock, razorpay).",
    )
    gateway_ref = models.CharField(
        max_length=200,
        blank=True,
        help_text="Gateway-side payment/order ID for reconciliation.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    exempt = models.BooleanField(
        default=False,
        help_text="True when the candidate is exempt from the fee.",
    )
    exempt_reason = models.TextField(
        blank=True,
        help_text="Human-readable reason for exemption.",
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when payment was confirmed.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Payment"
        ordering = ["-created_at"]

    def __str__(self):
        status = "EXEMPT" if self.exempt else self.status
        return f"Payment {self.application.application_id}: ₹{self.amount} ({status})"


# ── Phase 3: Requisition ─────────────────────────────────────────────────────


class VacancyRequisition(models.Model):
    """A request to create a new vacancy, routed through approval stages."""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("finance_approved", "Finance Approved"),
        ("reservation_certified", "Reservation Certified"),
        ("ca_approved", "CA Approved"),
        ("rejected", "Rejected"),
    ]

    post_name = models.CharField(
        max_length=200,
        help_text="Name of the post being requested.",
    )
    count = models.PositiveIntegerField(
        help_text="Number of positions requested.",
    )
    grade = models.CharField(
        max_length=20,
        help_text="Pay grade (e.g. E-5).",
    )
    justification = models.TextField(
        help_text="Business justification for the requisition.",
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="draft",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requisitions",
        help_text="Staff user who raised this requisition.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vacancy Requisition"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.post_name} x{self.count} ({self.get_status_display()})"


class RequisitionApproval(models.Model):
    """One approval step in the requisition workflow."""

    STAGE_CHOICES = [
        ("hod", "Head of Department"),
        ("hr", "HR Review"),
        ("finance", "Finance"),
        ("final", "Final Approval"),
    ]
    DECISION_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    requisition = models.ForeignKey(
        VacancyRequisition,
        on_delete=models.CASCADE,
        related_name="approvals",
        help_text="Requisition being approved.",
    )
    stage = models.CharField(
        max_length=20,
        choices=STAGE_CHOICES,
        help_text="Approval stage (hod, hr, finance, final).",
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requisition_approvals",
        help_text="Staff user who made the decision.",
    )
    decision = models.CharField(
        max_length=20,
        choices=DECISION_CHOICES,
        default="pending",
    )
    comments = models.TextField(
        blank=True,
        help_text="Approver's comments.",
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Requisition Approval"
        ordering = ["timestamp"]
        unique_together = [("requisition", "stage")]

    def __str__(self):
        return f"{self.requisition.post_name} — {self.get_stage_display()}: {self.get_decision_display()}"


class Corrigendum(models.Model):
    """A published correction / addendum to an advertisement.

    Each corrigendum increments the version counter per advertisement.
    Applicants are notified automatically on creation (via the view).
    """

    advertisement = models.ForeignKey(
        Advertisement,
        on_delete=models.CASCADE,
        related_name="corrigenda",
        help_text="Advertisement this corrigendum corrects.",
    )
    version = models.PositiveIntegerField(
        help_text="Sequential version number within the advertisement.",
    )
    changes_text = models.TextField(
        help_text="Description of what changed.",
    )
    published_date = models.DateField(
        help_text="Date the corrigendum was published.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to soft-hide without deleting.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Corrigendum"
        verbose_name_plural = "Corrigenda"
        ordering = ["-published_date"]
        unique_together = [("advertisement", "version")]

    def __str__(self):
        return f"Corrigendum v{self.version} — {self.advertisement.advt_number}"


# ── Phase 3: Document Verification ──────────────────────────────────────────


class DocumentVerification(models.Model):
    """Structured verification workflow for a candidate-submitted document.

    Auto-created (pending) whenever a new Document is uploaded.  A recruiter
    can then mark it verified or rejected with an optional comment; every
    transition writes an AuditEvent.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("verified", "Verified"),
        ("rejected", "Rejected"),
    ]

    document = models.OneToOneField(
        Document,
        on_delete=models.CASCADE,
        related_name="verification",
        help_text="The document under review.",
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="pending",
        help_text="Current verification status.",
    )
    verifier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_verifications",
        help_text="Staff user who verified or rejected the document.",
    )
    comments = models.TextField(
        blank=True,
        help_text="Verifier's notes or rejection reason.",
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the verify/reject action.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Document Verification"
        verbose_name_plural = "Document Verifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Verification({self.document.doc_type}) — {self.get_status_display()}"


# ── Phase 3: Interview ───────────────────────────────────────────────────────


class InterviewPanel(models.Model):
    """A panel convened to interview candidates for a post."""

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="interview_panels",
        help_text="Post this panel interviews for.",
    )
    name = models.CharField(
        max_length=200,
        help_text="Panel identifier (e.g. 'Panel A').",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="interview_panels",
        help_text="Staff users serving on this panel.",
    )
    external_members = models.JSONField(
        default=list,
        blank=True,
        help_text="External panel members as list of dicts (name, org, etc.).",
    )
    sitting_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Sitting fee per member (null if not applicable).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Interview Panel"
        verbose_name_plural = "Interview Panels"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Panel: {self.name} ({self.post.post_code})"


class InterviewSlot(models.Model):
    """A scheduled interview slot for one candidate, assigned to a panel."""

    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    panel = models.ForeignKey(
        InterviewPanel,
        on_delete=models.CASCADE,
        related_name="slots",
        help_text="Panel conducting the interview.",
    )
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="interview_slots",
        help_text="Application being interviewed.",
    )
    datetime = models.DateTimeField(
        help_text="Scheduled date and time of the interview.",
    )
    duration_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Duration of the interview in minutes.",
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default="scheduled",
        help_text="Current status of the slot.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Scheduling or logistics notes.",
    )

    class Meta:
        verbose_name = "Interview Slot"
        verbose_name_plural = "Interview Slots"
        ordering = ["datetime"]

    def __str__(self):
        return f"Slot({self.application.application_id}) — {self.get_status_display()}"


class InterviewScore(models.Model):
    """A score awarded by a panel member for an interview slot."""

    slot = models.ForeignKey(
        InterviewSlot,
        on_delete=models.CASCADE,
        related_name="scores",
        help_text="Interview slot this score belongs to.",
    )
    panel_member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interview_scores",
        help_text="Panel member who gave the score (null for anonymous/external).",
    )
    score = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        help_text="Score awarded (e.g. 7.5).",
    )
    comments = models.TextField(
        blank=True,
        help_text="Panel member's comments or justification.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Interview Score"
        verbose_name_plural = "Interview Scores"
        ordering = ["-created_at"]

    def __str__(self):
        member = self.panel_member or "External"
        return f"Score {self.score} by {member} ({self.slot.application.application_id})"


# ── Phase 3: Litigation ─────────────────────────────────────────────────────

LITIGATION_STATUS_CHOICES = [
    ("filed", "Filed"),
    ("hearing", "Hearing"),
    ("stay", "Stay Granted"),
    ("resolved", "Resolved"),
    ("dismissed", "Dismissed"),
]


class LitigationCase(models.Model):
    """Court case tracker — links a litigation matter to an application, post, or advertisement."""

    case_number = models.CharField(
        max_length=100,
        help_text="Court case number (e.g. WP/1234/2026).",
    )
    court = models.CharField(
        max_length=200,
        help_text="Court name (e.g. Gauhati High Court).",
    )
    petitioner = models.CharField(
        max_length=200,
        help_text="Name of the petitioner.",
    )
    application = models.ForeignKey(
        Application,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="litigation_cases",
        help_text="Linked application (if any).",
    )
    post = models.ForeignKey(
        Post,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="litigation_cases",
        help_text="Linked post (if any).",
    )
    advertisement = models.ForeignKey(
        Advertisement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="litigation_cases",
        help_text="Linked advertisement (if any).",
    )
    status = models.CharField(
        max_length=20,
        choices=LITIGATION_STATUS_CHOICES,
        default="filed",
        help_text="Current status of the case.",
    )
    interim_orders = models.JSONField(
        default=list,
        blank=True,
        help_text="List of interim orders (type, date, text).",
    )
    final_order_text = models.TextField(
        blank=True,
        help_text="Text of the final court order.",
    )
    filed_on = models.DateField(
        help_text="Date the case was filed.",
    )
    resolved_on = models.DateField(
        null=True,
        blank=True,
        help_text="Date the case was resolved (null if still active).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Litigation Case"
        verbose_name_plural = "Litigation Cases"
        ordering = ["-filed_on"]

    def __str__(self):
        return f"{self.case_number} — {self.court}"

    @property
    def has_active_stay(self):
        """True if case is active and has a stay_order in interim_orders."""
        if self.status in ("resolved", "dismissed"):
            return False
        return any(o.get("type") == "stay_order" for o in self.interim_orders)

    def add_interim_order(self, order_type, text, order_date=None):
        """Append an interim order to the JSONField."""
        from datetime import date as _date

        self.interim_orders = list(self.interim_orders) + [
            {
                "type": order_type,
                "date": str(order_date or _date.today()),
                "text": text,
            }
        ]
        self.save(update_fields=["interim_orders"])


# ── Phase 4: Joining Report ──────────────────────────────────────────────────


class JoiningReport(models.Model):
    """Candidate-submitted joining report after accepting an offer.

    Captures the formal joining details: date, designation, pay fixation,
    reporting officer, and whether all required documents have been submitted.
    One-to-one with Application (a candidate submits at most one joining report
    per application).
    """

    application = models.OneToOneField(
        Application,
        on_delete=models.CASCADE,
        related_name="joining_report",
        help_text="The application this joining report belongs to.",
    )
    joining_date = models.DateField(
        help_text="Date the candidate reported for duty.",
    )
    designation = models.CharField(
        max_length=200,
        help_text="Designation at the time of joining (e.g. Assistant Engineer).",
    )
    pay_fixation = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Pay fixation details (e.g. Level-7, ₹44,900/- in Pay Matrix).",
    )
    reported_to = models.CharField(
        max_length=200,
        help_text="Name and/or designation of the officer reported to.",
    )
    documents_submitted = models.BooleanField(
        default=False,
        help_text="Whether all required documents have been submitted at joining.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Joining Report"
        verbose_name_plural = "Joining Reports"
        ordering = ["-created_at"]

    def __str__(self):
        return f"JoiningReport({self.application.application_id}) — {self.joining_date}"


# ── Phase 4: Probation & Bond ────────────────────────────────────────────────


class ProbationRecord(models.Model):
    """Tracks probation period and bond obligation for a joined candidate."""

    application = models.OneToOneField(
        Application,
        on_delete=models.CASCADE,
        related_name="probation_record",
        help_text="The application this probation record belongs to.",
    )
    start_date = models.DateField(
        help_text="Date the probation period begins.",
    )
    end_date = models.DateField(
        help_text="Date the probation period ends.",
    )
    confirmed_on = models.DateField(
        null=True,
        blank=True,
        help_text="Date the employee was confirmed (null if still on probation).",
    )
    bond_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Bond amount in INR, if applicable.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Free-text notes about the probation or bond.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Probation Record"
        verbose_name_plural = "Probation Records"
        ordering = ["-created_at"]

    def __str__(self):
        status = "Confirmed" if self.confirmed_on else "On Probation"
        return f"{self.application.application_id} — {status}"

    @property
    def is_confirmed(self):
        """True if the employee has been confirmed."""
        return self.confirmed_on is not None

    @property
    def is_expired(self):
        """True if the probation end_date has passed without confirmation."""
        from datetime import date as _date

        return not self.is_confirmed and self.end_date < _date.today()


# ── Phase 4: Grievance / Appeal ─────────────────────────────────────────────

GRIEVANCE_STATUS_CHOICES = [
    ("filed", "Filed"),
    ("acknowledged", "Acknowledged"),
    ("investigating", "Investigating"),
    ("resolved", "Resolved"),
]


class Grievance(models.Model):
    """A candidate grievance/appeal filed through the portal.

    Workflow: filed → acknowledged → investigating → resolved.
    Staff assign and resolve; candidate is notified on acknowledgement.
    """

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="grievances",
        help_text="Candidate who filed the grievance.",
    )
    application = models.ForeignKey(
        Application,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grievances",
        help_text="Related application (optional).",
    )
    subject = models.CharField(
        max_length=300,
        help_text="Brief subject of the grievance.",
    )
    description = models.TextField(
        help_text="Detailed description of the grievance.",
    )
    status = models.CharField(
        max_length=20,
        choices=GRIEVANCE_STATUS_CHOICES,
        default="filed",
        help_text="Current workflow status.",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_grievances",
        help_text="Staff member assigned to handle this grievance.",
    )
    resolution_notes = models.TextField(
        blank=True,
        help_text="Notes on the resolution outcome.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Grievance"
        verbose_name_plural = "Grievances"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Grievance({self.candidate}) — {self.subject}"


# ── Phase 4: Police Verification ─────────────────────────────────────────────

POLICE_VERIFICATION_STATUS_CHOICES = [
    ("initiated", "Initiated"),
    ("in_progress", "In Progress"),
    ("cleared", "Cleared"),
    ("not_cleared", "Not Cleared"),
]


class PoliceVerification(models.Model):
    """Police verification record for an application.

    Tracks the lifecycle: initiated → in_progress → cleared / not_cleared.
    The report_file field holds the scanned police clearance certificate
    once received.  Every status transition writes an AuditEvent against
    the linked application.
    """

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="police_verifications",
        help_text="Application under police verification.",
    )
    district = models.CharField(
        max_length=200,
        help_text="Police district responsible for the verification (e.g. 'East Khasi Hills').",
    )
    status = models.CharField(
        max_length=15,
        choices=POLICE_VERIFICATION_STATUS_CHOICES,
        default="initiated",
        help_text="Current verification status.",
    )
    report_file = models.FileField(
        upload_to="police_reports/",
        blank=True,
        help_text="Scanned police clearance report (PDF/image).",
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_police_verifications",
        help_text="Staff member who initiated the verification.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes or remarks.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Police Verification"
        verbose_name_plural = "Police Verifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"PoliceVerification({self.application.application_id}) — {self.district} — {self.get_status_display()}"


# ── Phase 4: Medical Examination ────────────────────────────────────────────

MEDICAL_FITNESS_CHOICES = [
    ("pending", "Pending"),
    ("fit", "Fit"),
    ("unfit", "Unfit"),
]


class MedicalExam(models.Model):
    """Medical examination record for a candidate's application.

    Workflow:
      1. HR schedules the exam (hospital, date).
      2. Recruiter uploads the medical report file.
      3. HR certifies fitness (fit/unfit).
    Status changes are audited via AuditEvent.
    """

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="medical_exams",
        help_text="The application this medical exam is for.",
    )
    hospital = models.CharField(
        max_length=300,
        help_text="Hospital or medical facility name.",
    )
    exam_date = models.DateField(
        help_text="Scheduled or actual date of the medical examination.",
    )
    report_file = models.FileField(
        upload_to="medical_reports/%Y/%m/",
        blank=True,
        help_text="Uploaded medical report (PDF/image).",
    )
    fitness_status = models.CharField(
        max_length=10,
        choices=MEDICAL_FITNESS_CHOICES,
        default="pending",
        help_text="Fitness certification outcome.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes or remarks about the medical exam.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Medical Exam"
        verbose_name_plural = "Medical Exams"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Medical({self.application.application_id}) — {self.get_fitness_status_display()}"
