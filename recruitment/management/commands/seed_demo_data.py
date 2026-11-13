"""Populate the demo tenant with realistic data for every major workflow.

The base seed commands (``seed_cloud_data``, ``seed_portal_demo``,
``simulate_*``) cover advertisements, candidates, applications and a few
workflow records.  Several screens in the staff app (document verification,
fee reconciliation, requisitions, interviews, litigation, probation,
grievances, medical/police checks) stay empty on a fresh deployment.

This command fills those gaps in one idempotent pass.  It is safe to run more
than once: records are looked up by their natural key and only missing rows are
created.  Files use tiny generated PDFs so the demo does not depend on checked
in binaries.

Usage::

    python manage.py seed_demo_data
    python manage.py seed_demo_data --no-files   # skip storage uploads
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone
from django_tenants.utils import schema_context

# Fixed anchor dates keep repeat runs idempotent even when the real clock moves.
DEMO_TODAY = date(2026, 11, 13)


# ── Tiny valid PDF generator ─────────────────────────────────────────────────


def build_demo_pdf(title: str, lines: list[str]) -> bytes:
    """Return a small, valid single-page PDF with the given text."""

    def escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    operations = ["BT", "/F1 16 Tf", "50 790 Td", f"({escape(title)}) Tj", "0 -26 Td", "/F1 10 Tf"]
    for line in lines:
        operations.append(f"({escape(line)}) Tj")
        operations.append("0 -16 Td")
    operations.append("ET")
    stream = "\n".join(operations).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    parts: list[bytes] = [b"%PDF-1.4\n"]
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in parts))
        parts.append(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = sum(len(part) for part in parts)
    parts.append(b"xref\n0 6\n0000000000 65535 f \n")
    for index in range(1, 6):
        parts.append(f"{offsets[index]:010d} 00000 n \n".encode())
    parts.append(
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_offset).encode()
        + b"\n%%EOF\n"
    )
    return b"".join(parts)


# ── Demo content ────────────────────────────────────────────────────────────

FIRST_NAMES_F = [
    "Priya", "Sneha", "Ananya", "Kavita", "Neha", "Ritu", "Pooja", "Swati",
    "Meera", "Divya", "Shruti", "Nandini", "Aparna", "Jyoti", "Rekha",
]
FIRST_NAMES_M = [
    "Amit", "Rahul", "Vijay", "Sanjay", "Arjun", "Deepak", "Rohan", "Kiran",
    "Nikhil", "Saurabh", "Pranab", "Manoj", "Rajesh", "Ashish", "Pankaj",
]
LAST_NAMES = [
    "Sharma", "Patel", "Singh", "Reddy", "Verma", "Gupta", "Nair", "Joshi",
    "Mehta", "Das", "Kumar", "Rao", "Mishra", "Choudhury", "Borah",
    "Hazarika", "Gogoi", "Saikia", "Debbarma", "Brahma",
]

UNIVERSITIES = [
    "Gauhati University", "Assam Engineering College", "NIT Silchar",
    "IIT Guwahati", "Tezpur University", "Dibrugarh University",
    "North Eastern Hill University", "Jadavpur University",
]

EMPLOYERS = [
    ("NEEPCO", "psu"), ("NHPC Limited", "psu"), ("NTPC Limited", "psu"),
    ("Oil India Limited", "psu"), ("Larsen & Toubro", "private"),
    ("Tata Projects", "private"), ("Wapcos Limited", "govt"),
    ("Meghalaya Power Distribution Corporation", "govt"),
]

HOSPITALS = [
    "North Eastern Indira Gandhi Regional Institute of Health Sciences, Shillong",
    "Guwahati Medical College & Hospital",
    "Woodland Hospital, Shillong",
    "Apollo Hospitals, Guwahati",
]

POLICE_DISTRICTS = [
    "East Khasi Hills", "Kamrup Metropolitan", "West Tripura",
    "Papum Pare", "Imphal West", "Aizawl",
]

REQUISITIONS = [
    {
        "post_name": "Executive (Civil) — Hydro Projects",
        "count": 4,
        "grade": "E-5",
        "justification": "New hydro-electric project at Subansiri requires site civil engineers.",
        "status": "finance_approved",
    },
    {
        "post_name": "Executive (Finance)",
        "count": 3,
        "grade": "E-4",
        "justification": "Strengthen project accounting and GST compliance across regional offices.",
        "status": "submitted",
    },
    {
        "post_name": "Executive (HR)",
        "count": 2,
        "grade": "E-5",
        "justification": "Replace two retirements in the corporate HR team in 2027.",
        "status": "ca_approved",
    },
    {
        "post_name": "Executive (Safety)",
        "count": 2,
        "grade": "E-4",
        "justification": "Additional safety officers for the Kameng and Pare hydro projects.",
        "status": "rejected",
    },
    {
        "post_name": "Executive (Medical)",
        "count": 3,
        "grade": "E-3",
        "justification": "Expand occupational health coverage at remote project hospitals.",
        "status": "draft",
    },
    {
        "post_name": "Executive (Law)",
        "count": 1,
        "grade": "E-4",
        "justification": "In-house counsel for the growing litigation portfolio.",
        "status": "reservation_certified",
    },
]

NOTIFICATION_TEMPLATES = [
    (
        "application_received", "email", "Application Received — {advt_number}",
        "Dear {candidate_name},\n\nYour application for {post_name} ({advt_number}) has been received. Application ID: {application_id}.\n\nRegards,\nRecruitment Cell",
    ),
    (
        "shortlisted", "email", "You have been shortlisted — {post_name}",
        "Dear {candidate_name},\n\nYou have been shortlisted for {post_name}. Please keep your documents ready for verification.\n\nRegards,\nRecruitment Cell",
    ),
    (
        "interview_invite", "email", "Interview invitation — {post_name}",
        "Dear {candidate_name},\n\nYou are invited for an interview for {post_name} on {interview_date}. Please carry a photo ID.\n\nRegards,\nRecruitment Cell",
    ),
    (
        "offer_letter", "email", "Offer of appointment — {post_name}",
        "Dear {candidate_name},\n\nWe are pleased to offer you the position of {post_name}. The offer letter is available in your candidate portal.\n\nRegards,\nRecruitment Cell",
    ),
    (
        "rejection", "email", "Update on your application — {post_name}",
        "Dear {candidate_name},\n\nThank you for your interest in {post_name}. Your application was not shortlisted this time.\n\nRegards,\nRecruitment Cell",
    ),
    (
        "otp_login", "sms", "TalentFlow OTP",
        "Your TalentFlow verification code is {otp}. It expires in 10 minutes.",
    ),
]


class Command(BaseCommand):
    help = "Fill every demo workflow with realistic, idempotent sample data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-files",
            action="store_true",
            help="Skip placeholder PDF uploads (records still get sample metadata).",
        )

    def handle(self, *args, **options):
        self.use_files = not options["no_files"]
        schema_name = settings.DEMO_TENANT_SCHEMA

        connection.set_schema_to_public()
        from tenants.models import Client

        try:
            tenant = Client.objects.get(schema_name=schema_name)
        except Client.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f"Tenant '{schema_name}' not found. Run setup_tenant / seed_cloud_data first."
            ))
            return

        random.seed(20261113)
        with schema_context(schema_name):
            self._seed(tenant)

    # ── helpers ────────────────────────────────────────────────────────────
    def _pdf_file(self, path: str, title: str, lines: list[str]) -> str:
        if not self.use_files:
            # Keep the FileField name so templates can still render a URL.
            return path
        if default_storage.exists(path):
            return path
        return default_storage.save(path, ContentFile(build_demo_pdf(title, lines)))

    def _count(self, key: str, amount: int = 1):
        self.counts[key] = self.counts.get(key, 0) + amount

    # ── main seeding routine ───────────────────────────────────────────────
    def _seed(self, tenant):
        from accounts.models import User
        from consent.models import Consent, ConsentEvent
        from notifications.models import NotificationOutbox, NotificationTemplate
        from profiles.models import (
            AcademicRecord,
            CandidateProfile,
            ExamDisclosure,
            ProfileDocument,
            WorkExperience,
        )
        from recruitment.models import (
            Advertisement,
            Application,
            AuditEvent,
            BackgroundReport,
            Candidate,
            CommunicationLog,
            Corrigendum,
            Document,
            DocumentVerification,
            DuplicateFlag,
            EligibilityOverride,
            FetchedDocument,
            Grievance,
            InterviewPanel,
            InterviewScore,
            InterviewSlot,
            JoiningReport,
            LitigationCase,
            MedicalExam,
            OrgProfile,
            Payment,
            PoliceVerification,
            Post,
            PostBasedRoster,
            ProbationRecord,
            RequisitionApproval,
            Resume,
            VacancyRequisition,
        )
        from recruitment.roster import build_roster

        self.counts = {}
        now = timezone.now()
        self.stdout.write("  Seeding candidate profiles and academic history...")

        advertisement = (
            Advertisement.objects.filter(is_active=True)
            .order_by("-published_date")
            .first()
        )
        if advertisement is None:
            self.stdout.write(self.style.WARNING(
                "No active advertisement found. Run seed_cloud_data first."
            ))
            return

        posts = list(Post.objects.filter(advertisement=advertisement).order_by("id"))
        applications = list(
            Application.objects.select_related("candidate__portal_user", "post")
            .order_by("id")
        )
        candidates = list(Candidate.objects.order_by("id")) if applications else []
        portal_candidates = [
            cand for cand in candidates if cand.portal_user_id is not None
        ]

        staff = {user.username: user for user in User.objects.filter(is_staff=True)}
        hr = staff.get("a.sharma") or next(iter(staff.values()), None)
        recruiter = staff.get("r.mehta") or hr
        reviewer = staff.get("s.iyer") or hr
        admin = staff.get("admin") or hr

        profile_by_candidate = {}

        # ── Organisation profile polish ───────────────────────────────────
        org = OrgProfile.objects.first()
        if org:
            updates = {}
            if not org.footer_motto:
                updates["footer_motto"] = "Powering the North East, empowering the nation"
            if not org.sbi_epay_text:
                updates["sbi_epay_text"] = (
                    "Application fee: ₹500 (exempt for SC/ST/OBC/EWS/PwBD/female candidates). "
                    "Pay online through SBI ePay; keep the transaction reference for reconciliation."
                )
            if updates:
                OrgProfile.objects.filter(pk=org.pk).update(**updates)
                self._count("organisation profile")

        # ── Candidate profiles, academics, work history and exams ────────
        for index, candidate in enumerate(candidates):
            gender = "F" if index % 3 == 0 else "M"
            category = ("ur", "obc", "sc", "st", "ews")[index % 5]
            profile, created = CandidateProfile.objects.get_or_create(
                candidate=candidate,
                defaults={
                    "gender": gender,
                    "category": category,
                    "is_pwbd": index % 17 == 0,
                    "permanent_address": (
                        f"House {10 + index}, {random.choice(['Laitumkhrah', 'Beltola', 'Six Mile', 'Zoo Road'])}, "
                        f"Guwahati, Assam — 7810{index % 10:02d}"
                    ),
                    "current_address": (
                        f"C/o {random.choice(['NEEPCO Colony', 'Project Township'])}, "
                        f"{random.choice(['Shillong', 'Guwahati', 'Itanagar', 'Agartala'])}"
                    ),
                },
            )
            if created:
                self._count("candidate profiles")
            profile_by_candidate[candidate.pk] = profile

            discipline = random.choice([
                "Civil Engineering", "Mechanical Engineering", "Electrical Engineering",
                "Commerce", "Human Resource Management", "Law", "Medicine",
            ])
            board = random.choice(["CBSE", "SEBA", "AHSEC", "ICSE"])
            academic_rows = [
                {
                    "level": "10th",
                    "discipline": "General",
                    "university_board": board,
                    "year_passed": 2006 + (index % 6),
                    "marking_type": "percentage",
                    "score": str(round(66 + (index * 7) % 25, 1)),
                },
                {
                    "level": "12th",
                    "discipline": "Science" if index % 2 == 0 else "Commerce",
                    "university_board": board,
                    "year_passed": 2008 + (index % 6),
                    "marking_type": "percentage",
                    "score": str(round(62 + (index * 5) % 28, 1)),
                },
                {
                    "level": "ug",
                    "discipline": discipline,
                    "university_board": random.choice(UNIVERSITIES),
                    "year_passed": 2012 + (index % 5),
                    "marking_type": "cgpa" if index % 2 else "percentage",
                    "score": str(round(7.0 + (index % 4) * 0.3, 1)) if index % 2 else str(round(60 + (index * 3) % 30, 1)),
                    "is_ugc_recognized": True,
                },
            ]
            if index % 3 == 0:
                academic_rows.append({
                    "level": "pg",
                    "discipline": "MBA (HR)" if discipline == "Human Resource Management" else f"M.Tech ({discipline})",
                    "university_board": random.choice(UNIVERSITIES),
                    "year_passed": 2014 + (index % 5),
                    "marking_type": "percentage",
                    "score": str(round(65 + (index * 4) % 27, 1)),
                    "is_ugc_recognized": True,
                })
            for row in academic_rows:
                _, created = AcademicRecord.objects.get_or_create(
                    candidate=candidate,
                    level=row["level"],
                    defaults=row,
                )
                if created:
                    self._count("academic records")

            if index % 2 == 0:
                employer, org_type = random.choice(EMPLOYERS)
                start = date(2014 + (index % 5), 7, 1)
                experience_rows = [{
                    "org_name": employer,
                    "org_type": org_type,
                    "designation": f"Assistant Manager ({discipline.split()[0]})",
                    "start_date": start,
                    "end_date": None if index % 4 == 0 else start + timedelta(days=365 * 3),
                    "annual_ctc_lakhs": Decimal(str(8 + (index % 7))),
                    "turnover_cr": Decimal(str(1200 + index * 35)),
                }]
                if index % 6 == 0:
                    experience_rows.append({
                        "org_name": "NEEPCO",
                        "org_type": "psu",
                        "designation": "Graduate Engineer Trainee",
                        "start_date": start - timedelta(days=365 * 2),
                        "end_date": start,
                        "annual_ctc_lakhs": Decimal("6.5"),
                        "turnover_cr": Decimal("4200"),
                    })
                for row in experience_rows:
                    _, created = WorkExperience.objects.get_or_create(
                        candidate=candidate,
                        org_name=row["org_name"],
                        designation=row["designation"],
                        defaults=row,
                    )
                    if created:
                        self._count("work experience")

            if index % 3 == 0:
                _, created = ExamDisclosure.objects.get_or_create(
                    candidate=candidate,
                    defaults={
                        "exam_type": "both" if index % 6 == 0 else "gate",
                        "gate_year": 2024 if index % 2 else 2025,
                        "paper_code": random.choice(["CE", "ME", "EE", "CS", "IN"]),
                        "marks_out_100": Decimal(str(round(55 + (index % 30), 2))),
                        "gate_score": Decimal(str(round(520 + (index * 11) % 380, 2))),
                        "air": 50 + index * 37,
                        "ese_total_score": Decimal(str(round(700 + (index * 9) % 300, 2))) if index % 6 == 0 else None,
                        "public_disclosure_consent": index % 2 == 0,
                    },
                )
                if created:
                    self._count("exam disclosures")

        # ── Resume evaluation details on applications ─────────────────────
        evaluation_summaries = [
            "Strong technical fit with directly relevant hydro-project experience.",
            "Good functional depth; exposure to public-sector procurement is limited.",
            "Meets the advertised criteria, with strong communication and stakeholder skills.",
        ]
        for index, application in enumerate(applications[:24]):
            score = application.resume_score or 70
            Application.objects.filter(pk=application.pk).update(
                resume_evaluation={
                    "summary": evaluation_summaries[index % len(evaluation_summaries)],
                    "competencies": [
                        {"name": "Technical knowledge", "score": min(95, score + 4), "notes": "Assessed from qualifications and project history."},
                        {"name": "Relevant experience", "score": max(35, score - 6), "notes": "Compared against the post's minimum experience."},
                        {"name": "Communication", "score": min(92, score + 1), "notes": "Based on resume language and documented roles."},
                    ],
                    "positives": [
                        "Relevant PSU / infrastructure experience",
                        "Consistent academic record",
                        "Clear career progression",
                    ],
                    "concerns": [
                        "Notice period not stated" if index % 2 else "Limited exposure to the North East region",
                    ],
                },
                evaluation_notes="AI evaluation reviewed by the recruitment cell for the demo.",
            )
            self._count("resume evaluations")

        for application in applications:
            if application.status == "rejected" and not application.rejected_at_stage:
                application.rejected_at_stage = "document_verification"
                application.save(update_fields=["rejected_at_stage"])
                self._count("rejection stages")

        # ── Consent ledger for portal users ──────────────────────────────
        purposes = [
            ("application", "Processing my application for the advertised post."),
            ("digilocker", "Fetching my degree and identity documents from DigiLocker."),
            ("resume_parsing", "Parsing my resume with the automated evaluation agent."),
            ("background_check", "Conducting background and police verification if selected."),
            ("interview", "Recording interview notes and panel scores."),
        ]
        for index, candidate in enumerate(portal_candidates):
            portal_user = candidate.portal_user
            linked_app = candidate.applications.first()
            for purpose_index, (purpose, scope) in enumerate(purposes):
                consent, created = Consent.objects.get_or_create(
                    candidate_portal_user=portal_user,
                    purpose=purpose,
                    defaults={
                        "application": linked_app if purpose in ("application", "background_check") else None,
                        "scope_text": scope,
                        "expires_at": now + timedelta(days=365),
                        "ip_address": "127.0.0.1",
                        "user_agent": "Mozilla/5.0 (TalentFlow demo)",
                    },
                )
                if created:
                    ConsentEvent.objects.create(
                        consent=consent,
                        action="granted",
                        ip_address="127.0.0.1",
                        details="Consent granted through the candidate portal.",
                    )
                    self._count("consents")
            # One revoked consent and one expired consent make the ledger realistic.
            revoked = Consent.objects.filter(
                candidate_portal_user=portal_user, purpose="interview"
            ).first()
            if revoked and index == 0 and revoked.revoked_at is None:
                revoked.revoked_at = now - timedelta(days=4)
                revoked.save(update_fields=["revoked_at"])
                ConsentEvent.objects.get_or_create(
                    consent=revoked,
                    action="revoked",
                    defaults={"details": "Candidate withdrew interview recording consent."},
                )
            expired = Consent.objects.filter(
                candidate_portal_user=portal_user, purpose="resume_parsing"
            ).first()
            if expired and index == 1 and expired.expires_at and expired.expires_at > now:
                expired.expires_at = now - timedelta(days=2)
                expired.save(update_fields=["expires_at"])
                ConsentEvent.objects.get_or_create(
                    consent=expired,
                    action="expired",
                    defaults={"details": "Resume parsing consent reached its expiry date."},
                )

        # ── Portal users get profile documents and parsed resumes ─────────
        for index, candidate in enumerate(portal_candidates):
            for doc_type, note in (
                ("dob", "Birth certificate / Class X admit card"),
                ("academic", "Consolidated marksheet and degree certificate"),
            ):
                path = f"profile_documents/demo/{candidate.pk}_{doc_type}.pdf"
                stored = self._pdf_file(
                    path,
                    f"Demo {doc_type.upper()} document — {candidate.first_name} {candidate.last_name}",
                    [
                        f"Candidate: {candidate.first_name} {candidate.last_name}",
                        f"Email: {candidate.email}",
                        f"Document type: {doc_type}",
                        "This is a generated placeholder for the TalentFlow demo.",
                    ],
                )
                _, created = ProfileDocument.objects.get_or_create(
                    candidate=candidate,
                    doc_type=doc_type,
                    defaults={"file": stored, "note": note},
                )
                if created:
                    self._count("profile documents")

        resume_candidates = portal_candidates + [
            cand for cand in candidates[:5] if cand not in portal_candidates
        ]
        resumes_to_create = []
        for candidate in resume_candidates:
            if Resume.objects.filter(candidate=candidate).exists():
                continue
            path = f"resumes/demo/{candidate.pk}.pdf"
            stored = self._pdf_file(
                path,
                f"Curriculum Vitae — {candidate.first_name} {candidate.last_name}",
                [
                    f"Name: {candidate.first_name} {candidate.last_name}",
                    f"Email: {candidate.email}",
                    f"Mobile: {candidate.mobile}",
                    "Skills: project management, stakeholder coordination, data analysis",
                    "Experience: 7 years in a CPSU / large infrastructure organisation",
                    "Education: Bachelor of Engineering from a recognised university",
                ],
            )
            resumes_to_create.append(Resume(
                candidate=candidate,
                file=stored,
                parsed_json={
                    "name": f"{candidate.first_name} {candidate.last_name}",
                    "email": candidate.email,
                    "phone": candidate.mobile,
                    "skills": ["Project Management", "Stakeholder Coordination", "Data Analysis", "MS Project"],
                    "experience_years": 7,
                    "current_employer": random.choice(EMPLOYERS)[0],
                    "education": "Bachelor of Engineering",
                },
                confidence=Decimal("0.94"),
                parse_status="parsed",
                parsed_at=now,
            ))
        if resumes_to_create:
            # bulk_create intentionally bypasses the OCR signal: these are
            # already-parsed demo resumes, not real uploads.
            Resume.objects.bulk_create(resumes_to_create)
            self._count("parsed resumes", len(resumes_to_create))

        # ── Document verification ─────────────────────────────────────────
        self.stdout.write("  Seeding documents, verification and DigiLocker records...")
        doc_apps = [
            app for app in applications
            if app.status in ("document_verification", "shortlisted")
        ][:20]
        for app_index, application in enumerate(doc_apps):
            for doc_index, doc_type in enumerate(("degree", "dob")):
                path = f"documents/demo/{application.application_id}/{doc_type}.pdf"
                stored = self._pdf_file(
                    path,
                    f"{doc_type.title()} certificate — {application.application_id}",
                    [
                        f"Application: {application.application_id}",
                        f"Candidate: {application.candidate.first_name} {application.candidate.last_name}",
                        f"Post: {application.post.name} ({application.post.post_code})",
                        "Generated placeholder document for the TalentFlow demo.",
                    ],
                )
                document, created = Document.objects.get_or_create(
                    application=application,
                    doc_type=doc_type,
                    defaults={
                        "file": stored,
                        "extracted_data": {
                            "doc_type": doc_type,
                            "candidate_name": f"{application.candidate.first_name} {application.candidate.last_name}",
                            "confidence": 0.96,
                            "pages": 1,
                        },
                    },
                )
                if created:
                    self._count("documents")

                verification, _ = DocumentVerification.objects.get_or_create(document=document)
                status = ("pending", "verified", "rejected")[(app_index + doc_index) % 3]
                if verification.status == "pending" and status != "pending":
                    verification.status = status
                    verification.verifier = hr if status == "verified" else recruiter
                    verification.comments = (
                        "All details match the application."
                        if status == "verified"
                        else "Uploaded copy is illegible; a clearer scan is required."
                    )
                    verification.verified_at = now - timedelta(days=3 + app_index)
                    verification.save()
                    document.is_verified = status == "verified"
                    document.verified_at = verification.verified_at if status == "verified" else None
                    document.save(update_fields=["is_verified", "verified_at"])
                    self._count(f"documents {status}")

        # ── DigiLocker / fetched documents ────────────────────────────────
        portal_apps = [app for app in applications if app.candidate.portal_user_id]
        for app_index, application in enumerate(portal_apps[:6]):
            for doc_type in ("aadhaar", "degree"):
                _, created = FetchedDocument.objects.get_or_create(
                    application=application,
                    doc_type=doc_type,
                    defaults={
                        "issuer": "DigiLocker" if doc_type == "aadhaar" else "National Academic Depository",
                        "issue_date": "2024-06-15",
                        "data": {
                            "name": f"{application.candidate.first_name} {application.candidate.last_name}",
                            "masked_id": "XXXX-XXXX-4321" if doc_type == "aadhaar" else "NAD-2024-8891",
                            "verified": True,
                        },
                        "signature_valid": True,
                        "source": "digilocker",
                    },
                )
                if created:
                    self._count("fetched documents")

        # ── Background reports with human review states ───────────────────
        self.stdout.write("  Seeding background checks, duplicates and communications...")
        for index, application in enumerate(applications[:40]):
            status = ("pending", "explained", "reviewed")[index % 3]
            candidate = application.candidate
            facts = {
                "identity": {
                    "name": f"{candidate.first_name} {candidate.last_name}",
                    "dob": str(candidate.date_of_birth) if candidate.date_of_birth else "",
                    "email": candidate.email,
                    "mobile": candidate.mobile,
                },
                "academic_summary": "3 qualifications verified, no discrepancy found",
                "employment_gap_months": 0 if index % 4 else 6,
                "criminal_record": "none declared",
                "address_match": "partial" if index % 3 else "exact",
                "social_media_flags": [],
            }
            BackgroundReport.objects.filter(application=application).update(
                facts=facts,
                status=status,
                candidate_explanation=(
                    "The six-month gap was for a family relocation; supporting documents were attached."
                    if status == "explained" else ""
                ),
                reviewer_notes=(
                    "Explanation accepted. No adverse finding."
                    if status == "reviewed" else ""
                ),
                reviewed_by=hr if status == "reviewed" else None,
                reviewed_at=now - timedelta(days=5) if status == "reviewed" else None,
            )
        self._count("background reports", min(len(applications), 40))

        # ── Duplicate application flags ───────────────────────────────────
        duplicate_pairs = []
        for candidate in candidates:
            cand_apps = list(candidate.applications.all()[:2])
            if len(cand_apps) >= 2:
                duplicate_pairs.append((candidate, cand_apps[0], cand_apps[1]))
            if len(duplicate_pairs) >= 4:
                break
        resolutions = ("pending", "genuine_duplicate", "false_positive", "merged")
        for index, (candidate, app_a, app_b) in enumerate(duplicate_pairs):
            resolution = resolutions[index % len(resolutions)]
            _, created = DuplicateFlag.objects.get_or_create(
                candidate=candidate,
                application_a=app_a,
                application_b=app_b,
                defaults={
                    "confidence": 80 - index * 6,
                    "match_fields": ["email", "mobile", "date_of_birth"],
                    "resolution": resolution,
                    "resolved_by": hr if resolution != "pending" else None,
                    "resolved_at": now - timedelta(days=2 + index) if resolution != "pending" else None,
                },
            )
            if created:
                self._count("duplicate flags")

        # ── Communication history ─────────────────────────────────────────
        existing_logs = set(
            CommunicationLog.objects.values_list("application_id", "comm_type")
        )
        logs = []
        for application in applications:
            candidate = application.candidate
            common = {
                "application": application,
                "channel": "email" if candidate.email else "portal",
            }
            entries = [(
                "acknowledgement",
                f"Application Received — {application.application_id}",
                f"Dear {candidate.first_name}, your application for {application.post.name} has been received.",
            )]
            if application.status in ("shortlisted", "interview", "offered", "joined"):
                entries.append((
                    "status_update",
                    f"Shortlisted — {application.post.name}",
                    f"Dear {candidate.first_name}, you have been shortlisted for {application.post.name}.",
                ))
            if application.status in ("interview", "offered", "joined"):
                entries.append((
                    "interview_invite",
                    f"Interview invitation — {application.post.name}",
                    f"Dear {candidate.first_name}, your interview is scheduled. Please check the portal for details.",
                ))
            if application.status in ("offered", "joined"):
                entries.append((
                    "offer",
                    f"Offer of appointment — {application.post.name}",
                    f"Dear {candidate.first_name}, please find your offer for {application.post.name} in the portal.",
                ))
            if application.status == "rejected":
                entries.append((
                    "rejection",
                    f"Update on your application — {application.post.name}",
                    f"Dear {candidate.first_name}, your application was not shortlisted this time.",
                ))
            for comm_type, subject, body in entries:
                key = (application.pk, comm_type)
                if key in existing_logs:
                    continue
                logs.append(CommunicationLog(
                    application=application,
                    channel=common["channel"],
                    comm_type=comm_type,
                    subject=subject,
                    body=body,
                    read_at=now - timedelta(days=1) if comm_type == "acknowledgement" else None,
                ))
        if logs:
            CommunicationLog.objects.bulk_create(logs)
            self._count("communication logs", len(logs))

        # ── Audit trail ───────────────────────────────────────────────────
        audit_rows = []
        for index, application in enumerate(applications):
            if application.status != "received" and not AuditEvent.objects.filter(
                application=application,
                field_name="status",
                old_value="received",
                new_value=application.status,
            ).exists():
                audit_rows.append(AuditEvent(
                    actor=hr if index % 2 == 0 else recruiter,
                    tenant_schema=tenant.schema_name,
                    application=application,
                    field_name="status",
                    old_value="received",
                    new_value=application.status,
                    reason="Workflow progression recorded by the demo seed.",
                ))
            if application.resume_score and not AuditEvent.objects.filter(
                application=application,
                field_name="resume_score",
                old_value="0",
                new_value=str(application.resume_score),
            ).exists():
                audit_rows.append(AuditEvent(
                    actor=reviewer,
                    tenant_schema=tenant.schema_name,
                    application=application,
                    field_name="resume_score",
                    old_value="0",
                    new_value=str(application.resume_score),
                    reason="Resume evaluation agent score.",
                ))
        if audit_rows:
            AuditEvent.objects.bulk_create(audit_rows)
            self._count("audit events", len(audit_rows))

        # ── Eligibility overrides ─────────────────────────────────────────
        override_apps = [
            app for app in applications
            if app.status in ("rejected", "document_verification", "shortlisted")
        ][:3]
        override_reasons = [
            "Relevant PSU experience was not captured by the automated parser; manually verified.",
            "Age relaxation applies under the Ex-servicemen category.",
            "Equivalent qualification accepted as per the advertisement's general conditions.",
        ]
        for index, application in enumerate(override_apps):
            _, created = EligibilityOverride.objects.get_or_create(
                application=application,
                defaults={
                    "verdict": index != 0,
                    "reason": override_reasons[index % len(override_reasons)],
                    "overridden_by": hr,
                },
            )
            if created:
                self._count("eligibility overrides")

        # ── Payments / fee reconciliation ────────────────────────────────
        self.stdout.write("  Seeding payments, DoPT rosters and requisitions...")
        for index, application in enumerate(applications):
            profile = profile_by_candidate.get(application.candidate_id)
            exempt = bool(profile and (
                profile.category in ("sc", "st", "obc", "ews")
                or profile.gender == "F"
                or profile.is_pwbd
            ))
            if exempt:
                status = "completed" if application.status != "rejected" else "failed"
                reason = "Fee exemption: reserved category / female / PwBD candidate."
            else:
                status = "completed" if application.status not in ("rejected", "received") else (
                    "pending" if index % 5 == 0 else "completed"
                )
                reason = ""
            Payment.objects.update_or_create(
                application=application,
                defaults={
                    "amount": Decimal("500.00"),
                    "gateway": "sbi_epay",
                    "gateway_ref": f"SBI{application.pk:010d}",
                    "status": status,
                    "exempt": exempt,
                    "exempt_reason": reason,
                    "paid_at": now - timedelta(days=10 + index % 20) if status == "completed" else None,
                },
            )
        self._count("payments", len(applications))

        # ── DoPT post-based rosters ───────────────────────────────────────
        for post in posts:
            _, created = PostBasedRoster.objects.get_or_create(
                post=post,
                defaults={
                    "cycle_start_year": 2026,
                    "roster_points": build_roster(post, 2026),
                    "current_position": 1 + (post.pk % 6),
                    "liaison_officer": hr,
                    "certified_on": now - timedelta(days=30),
                    "certified_by": admin,
                },
            )
            if created:
                self._count("post rosters")

        # ── Requisitions and approval history ─────────────────────────────
        stage_order = ("finance", "hr", "final")
        stage_roles = {"finance": recruiter, "hr": hr, "final": admin}
        approved_counts = {
            "draft": 0,
            "submitted": 0,
            "finance_approved": 1,
            "reservation_certified": 2,
            "ca_approved": 3,
            "rejected": 0,
        }
        for spec in REQUISITIONS:
            requisition = VacancyRequisition.objects.filter(
                post_name=spec["post_name"], grade=spec["grade"]
            ).first()
            if requisition is None:
                requisition = VacancyRequisition.objects.create(
                    post_name=spec["post_name"],
                    count=spec["count"],
                    grade=spec["grade"],
                    justification=spec["justification"],
                    status=spec["status"],
                    created_by=hr,
                )
                self._count("requisitions")
            elif requisition.status != spec["status"]:
                requisition.status = spec["status"]
                requisition.save(update_fields=["status"])

            approved = approved_counts[spec["status"]]
            for stage_index, stage in enumerate(stage_order):
                if spec["status"] == "draft":
                    break
                if spec["status"] == "rejected":
                    if stage != "finance":
                        break
                    decision = "rejected"
                elif stage_index < approved:
                    decision = "approved"
                elif stage_index == approved:
                    decision = "pending"
                else:
                    break
                _, created = RequisitionApproval.objects.update_or_create(
                    requisition=requisition,
                    stage=stage,
                    defaults={
                        "approver": stage_roles[stage] if decision != "pending" else None,
                        "decision": decision,
                        "comments": {
                            "approved": "Verified against the manpower plan and budget.",
                            "rejected": "Deferred; the vacancy will be reviewed in the next cycle.",
                            "pending": "",
                        }[decision],
                    },
                )
                if created:
                    self._count("requisition approvals")

        # ── Corrigenda ────────────────────────────────────────────────────
        corrigenda = [
            (1, "The last date for online application is extended from 28.02.2027 to 31.03.2027.", date(2026, 11, 5)),
            (2, "Experience requirements for FTB/4/HR/13 revised to four years in hydro power projects.", date(2026, 11, 10)),
        ]
        for version, text, published in corrigenda:
            _, created = Corrigendum.objects.get_or_create(
                advertisement=advertisement,
                version=version,
                defaults={
                    "changes_text": text,
                    "published_date": published,
                    "is_active": True,
                },
            )
            if created:
                self._count("corrigenda")

        # ── Interview panels, slots and scores ────────────────────────────
        self.stdout.write("  Seeding interviews, litigation and post-selection records...")
        interview_posts = [
            post for post in posts
            if any(app.post_id == post.pk and app.status == "interview" for app in applications)
        ][:4]
        panel_members = [user for user in (hr, recruiter, reviewer) if user]
        for post_index, post in enumerate(interview_posts):
            panel, created = InterviewPanel.objects.get_or_create(
                post=post,
                name=f"Panel {'ABCD'[post_index % 4]}",
                defaults={
                    "sitting_fee": Decimal("5000.00"),
                    "external_members": [
                        {"name": "Dr. A. K. Baruah", "org": "Gauhati University"},
                        {"name": "Shri M. L. Nongrum", "org": "Retired CMD, MePDCL"},
                    ],
                },
            )
            if created:
                self._count("interview panels")
            panel.members.set(panel_members)

            post_apps = [
                app for app in applications
                if app.post_id == post.pk and app.status in ("interview", "offered", "joined")
            ][:5]
            for slot_index, application in enumerate(post_apps):
                completed = slot_index < 3
                slot, slot_created = InterviewSlot.objects.get_or_create(
                    panel=panel,
                    application=application,
                    defaults={
                        "datetime": (
                            now - timedelta(days=14 - slot_index)
                            if completed
                            else now + timedelta(days=slot_index - 1)
                        ),
                        "duration_minutes": 30,
                        "status": "completed" if completed else "scheduled",
                        "notes": (
                            "Interview completed; scores submitted by the panel."
                            if completed
                            else "Candidate asked to carry original documents."
                        ),
                    },
                )
                if slot_created:
                    self._count("interview slots")
                if completed:
                    for member_index, member in enumerate(panel_members):
                        _, score_created = InterviewScore.objects.get_or_create(
                            slot=slot,
                            panel_member=member,
                            defaults={
                                "score": Decimal(str(7.0 + ((slot_index + member_index) % 4) * 0.5)),
                                "comments": (
                                    "Strong technical answers and relevant PSU experience."
                                    if member_index % 2 == 0
                                    else "Good communication; some gaps in project finance exposure."
                                ),
                            },
                        )
                        if score_created:
                            self._count("interview scores")

        # ── Litigation tracker ────────────────────────────────────────────
        rejected_apps = [app for app in applications if app.status == "rejected"]
        shortlisted_apps = [app for app in applications if app.status == "shortlisted"]
        cases = [
            {
                "case_number": "WP(C)/1234/2026",
                "court": "Gauhati High Court",
                "petitioner": "Rahul Sharma",
                "application": rejected_apps[0] if rejected_apps else None,
                "post": posts[0] if posts else None,
                "status": "hearing",
                "interim_orders": [{
                    "type": "stay_order",
                    "date": "2026-10-28",
                    "text": "Operation of the rejection order stayed pending final hearing.",
                }],
                "filed_on": date(2026, 9, 12),
            },
            {
                "case_number": "WP(C)/567/2025",
                "court": "Gauhati High Court",
                "petitioner": "Anjali Das",
                "application": shortlisted_apps[0] if shortlisted_apps else None,
                "post": posts[1] if len(posts) > 1 else None,
                "status": "resolved",
                "interim_orders": [],
                "final_order_text": "Petition disposed of with a direction to reconsider the candidature within eight weeks.",
                "filed_on": date(2025, 11, 4),
                "resolved_on": date(2026, 4, 18),
            },
            {
                "case_number": "CAT/GA/89/2026",
                "court": "Central Administrative Tribunal, Guwahati",
                "petitioner": "NEEPCO Employees' Association",
                "application": None,
                "post": posts[2] if len(posts) > 2 else None,
                "status": "filed",
                "interim_orders": [],
                "filed_on": date(2026, 10, 2),
            },
            {
                "case_number": "WP(C)/901/2026",
                "court": "High Court of Meghalaya",
                "petitioner": "K. Marbaniang",
                "application": None,
                "post": posts[3] if len(posts) > 3 else None,
                "status": "dismissed",
                "interim_orders": [],
                "final_order_text": "The writ petition is dismissed as withdrawn with liberty to approach the proper forum.",
                "filed_on": date(2026, 6, 21),
                "resolved_on": date(2026, 9, 30),
            },
        ]
        for case in cases:
            _, created = LitigationCase.objects.get_or_create(
                case_number=case["case_number"],
                defaults={
                    "court": case["court"],
                    "petitioner": case["petitioner"],
                    "application": case["application"],
                    "post": case["post"],
                    "advertisement": advertisement,
                    "status": case["status"],
                    "interim_orders": case["interim_orders"],
                    "final_order_text": case.get("final_order_text", ""),
                    "filed_on": case["filed_on"],
                    "resolved_on": case.get("resolved_on"),
                },
            )
            if created:
                self._count("litigation cases")

        # ── Joining reports and probation ────────────────────────────────
        joined_apps = [app for app in applications if app.status == "joined"]
        for index, application in enumerate(joined_apps):
            joining_date = DEMO_TODAY - timedelta(days=400 + index * 45)
            _, created = JoiningReport.objects.get_or_create(
                application=application,
                defaults={
                    "joining_date": joining_date,
                    "designation": application.post.name,
                    "pay_fixation": application.post.pay_scale or "Level-7, ₹44,900/- in Pay Matrix",
                    "reported_to": "Head of HR, NEEPCO",
                    "documents_submitted": True,
                },
            )
            if created:
                self._count("joining reports")

            _, created = ProbationRecord.objects.get_or_create(
                application=application,
                defaults={
                    "start_date": joining_date,
                    "end_date": joining_date + timedelta(days=730),
                    "confirmed_on": joining_date + timedelta(days=365) if index < 2 else None,
                    "bond_amount": Decimal("300000.00") if index % 2 == 0 else None,
                    "notes": (
                        "Two-year probation with a three-year service bond for project-site postings."
                        if index % 2 == 0
                        else "Standard probation; confirmation review due after 24 months."
                    ),
                },
            )
            if created:
                self._count("probation records")

        # ── Grievances ────────────────────────────────────────────────────
        self.stdout.write("  Seeding grievances, medical/police checks and templates...")
        grievance_apps = portal_apps[:5] or applications[:5]
        grievance_specs = [
            ("filed", "Application fee debited twice", "The SBI ePay page timed out and the fee was debited again.", ""),
            ("acknowledged", "Correction in date of birth", "The date of birth printed on the application is incorrect.", ""),
            ("investigating", "Not allowed to upload category certificate", "The portal rejected a valid OBC-NCL certificate.", ""),
            ("resolved", "Request for scribe", "Requested a scribe for the written test as a PwBD candidate.", "Scribe approved and candidate informed by email."),
            ("resolved", "Rejected without eligibility review", "The application was rejected despite meeting the advertised criteria.", "Eligibility re-checked; candidature restored and applicant informed."),
        ]
        for index, application in enumerate(grievance_apps):
            status, subject, description, resolution = grievance_specs[index % len(grievance_specs)]
            Grievance.objects.update_or_create(
                candidate=application.candidate,
                subject=subject,
                defaults={
                    "application": application,
                    "description": description,
                    "status": status,
                    "assigned_to": None if status == "filed" else (recruiter if index % 2 else hr),
                    "resolution_notes": resolution,
                },
            )
            self._count("grievances")

        # ── Medical examinations ─────────────────────────────────────────
        medical_apps = [
            app for app in applications if app.status in ("offered", "joined")
        ][:12]
        for index, application in enumerate(medical_apps):
            exam_date = DEMO_TODAY + timedelta(days=7 + index * 2)
            hospital = HOSPITALS[index % len(HOSPITALS)]
            fitness = ("fit", "pending", "unfit")[index % 3]
            exam, created = MedicalExam.objects.get_or_create(
                application=application,
                exam_date=exam_date,
                defaults={
                    "hospital": hospital,
                    "fitness_status": fitness,
                    "notes": "Pre-employment medical examination as per NEEPCO standards.",
                },
            )
            if created:
                self._count("medical exams")
            if fitness == "fit" and self.use_files and not exam.report_file:
                exam.report_file = self._pdf_file(
                    f"medical_reports/demo/{application.application_id}.pdf",
                    f"Medical fitness certificate — {application.application_id}",
                    [
                        f"Candidate: {application.candidate.first_name} {application.candidate.last_name}",
                        f"Hospital: {hospital}",
                        "Fitness status: FIT for employment",
                        "Generated placeholder for the TalentFlow demo.",
                    ],
                )
                exam.save(update_fields=["report_file", "updated_at"])

        # ── Police verification ──────────────────────────────────────────
        police_apps = [
            app for app in applications if app.status in ("offered", "joined")
        ][:12]
        for index, application in enumerate(police_apps):
            district = POLICE_DISTRICTS[index % len(POLICE_DISTRICTS)]
            status = ("cleared", "in_progress", "initiated", "cleared")[index % 4]
            verification, created = PoliceVerification.objects.get_or_create(
                application=application,
                district=district,
                defaults={
                    "status": status,
                    "initiated_by": hr,
                    "notes": "Verification initiated as part of pre-appointment formalities.",
                },
            )
            if created:
                self._count("police verifications")
            if status == "cleared" and self.use_files and not verification.report_file:
                verification.report_file = self._pdf_file(
                    f"police_reports/demo/{application.application_id}.pdf",
                    f"Police verification report — {application.application_id}",
                    [
                        f"Candidate: {application.candidate.first_name} {application.candidate.last_name}",
                        f"District: {district}",
                        "Verification status: CLEARED — no adverse record found.",
                        "Generated placeholder for the TalentFlow demo.",
                    ],
                )
                verification.save(update_fields=["report_file"])

        # ── Notification templates and outbox states ──────────────────────
        for name, channel, subject, body in NOTIFICATION_TEMPLATES:
            _, created = NotificationTemplate.objects.update_or_create(
                name=name,
                defaults={"channel": channel, "subject": subject, "body_template": body},
            )
            if created:
                self._count("notification templates")

        queued = list(NotificationOutbox.objects.filter(status="queued").order_by("id"))
        for index, notification in enumerate(queued):
            if index < 80:
                notification.status = "sent"
            elif index < 86:
                notification.status = "failed"
                notification.error = "SMTP timeout in the sandbox mail relay."
            else:
                break
        if queued:
            NotificationOutbox.objects.bulk_update(
                [n for n in queued[:86] if n.status != "queued"], ["status", "error"]
            )

        # ── Final summary ─────────────────────────────────────────────────
        summary = ", ".join(f"{key}: {value}" for key, value in sorted(self.counts.items()))
        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready for '{tenant.name}' ({tenant.schema_name})."
        ))
        if summary:
            self.stdout.write(f"  {summary}")
        self.stdout.write(
            "  Run seed_demo_data again at any time; existing rows are left untouched."
        )
