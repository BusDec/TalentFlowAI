"""Candidate profile models — TalentBridge-style bio, academics, work, exams.

Per-tenant schema (same as recruitment). Attached to a recruitment.Candidate so
a profile follows the candidate across applications.
"""

from django.db import models

GENDER_CHOICES = (("M", "Male"), ("F", "Female"), ("O", "Other"))


class CandidateProfile(models.Model):
    """Extended bio for a candidate (single row per candidate)."""

    CATEGORY_CHOICES = (
        ("ur", "General (UR)"),
        ("obc", "OBC (NCL)"),
        ("sc", "SC"),
        ("st", "ST"),
        ("ews", "EWS"),
    )

    candidate = models.OneToOneField(
        "recruitment.Candidate", on_delete=models.CASCADE, related_name="profile"
    )
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, blank=True)
    is_pwbd = models.BooleanField(default=False)
    aadhar_no = models.CharField(max_length=20, blank=True, help_text="Aadhaar number (proof document required)")
    permanent_address = models.TextField(blank=True)
    current_address = models.TextField(blank=True)
    current_same_as_permanent = models.BooleanField(
        default=False, help_text="Check to reuse the permanent address as the current address."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Candidate Profile"

    def __str__(self):
        return f"Profile: {self.candidate}"

    @property
    def effective_current_address(self):
        if self.current_same_as_permanent:
            return self.permanent_address
        return self.current_address


class AcademicRecord(models.Model):
    """One row per academic qualification (SSC/12th/UG/PG...)."""

    LEVEL_CHOICES = (
        ("10th", "SSC / 10th"),
        ("12th", "HSC / 12th"),
        ("diploma", "Diploma"),
        ("ug", "Graduate (UG)"),
        ("pg", "Post-graduate (PG)"),
        ("other", "Other"),
    )
    MARKING_CHOICES = (("percentage", "Percentage"), ("cgpa", "CGPA"), ("grade", "Grade"))

    candidate = models.ForeignKey(
        "recruitment.Candidate", on_delete=models.CASCADE, related_name="academic_records"
    )
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    discipline = models.CharField(max_length=200, blank=True)
    university_board = models.CharField(max_length=200, blank=True)
    year_passed = models.PositiveIntegerField(null=True, blank=True)
    marking_type = models.CharField(max_length=20, choices=MARKING_CHOICES, default="percentage")
    score = models.CharField(max_length=20, blank=True)
    is_ugc_recognized = models.BooleanField(default=False)

    class Meta:
        ordering = ["-year_passed"]

    def __str__(self):
        return f"{self.get_level_display()} - {self.discipline or self.university_board}"


class WorkExperience(models.Model):
    """One row per employment record."""

    ORG_TYPE_CHOICES = (
        ("psu", "PSU"),
        ("private", "Private"),
        ("govt", "Government"),
        ("other", "Other"),
    )

    candidate = models.ForeignKey(
        "recruitment.Candidate", on_delete=models.CASCADE, related_name="work_experiences"
    )
    org_name = models.CharField(max_length=200)
    org_type = models.CharField(max_length=20, choices=ORG_TYPE_CHOICES, blank=True)
    designation = models.CharField(max_length=200, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    annual_ctc_lakhs = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    turnover_cr = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.designation or 'Role'} @ {self.org_name}"


class ExamDisclosure(models.Model):
    """GATE / ESE disclosure (public-exam score disclosure)."""

    EXAM_CHOICES = (("gate", "GATE"), ("ese", "ESE"), ("both", "GATE + ESE"))

    candidate = models.OneToOneField(
        "recruitment.Candidate", on_delete=models.CASCADE, related_name="exam_disclosure"
    )
    exam_type = models.CharField(max_length=10, choices=EXAM_CHOICES, blank=True)
    gate_year = models.PositiveIntegerField(null=True, blank=True)
    paper_code = models.CharField(max_length=20, blank=True)
    marks_out_100 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    gate_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    air = models.PositiveIntegerField(null=True, blank=True, help_text="All India Rank")
    ese_total_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    public_disclosure_consent = models.BooleanField(
        default=False, help_text="Consent to disclose the score publicly in the merit list."
    )

    def __str__(self):
        return f"Exam: {self.get_exam_type_display()} {self.gate_year or ''}".strip()


class ProfileDocument(models.Model):
    """Scanned proof document attached to a candidate profile."""

    DOC_TYPE_CHOICES = (
        ("dob", "Date of Birth Proof"),
        ("aadhar", "Aadhaar"),
        ("academic", "Academic Record"),
        ("work_ex", "Work Experience"),
        ("public_exam", "Public Exam Score"),
        ("certificate", "Certificate"),
        ("other", "Other"),
    )

    candidate = models.ForeignKey(
        "recruitment.Candidate", on_delete=models.CASCADE, related_name="profile_documents"
    )
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES)
    file = models.FileField(upload_to="profile_documents/")
    note = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.get_doc_type_display()} - {self.candidate}"
