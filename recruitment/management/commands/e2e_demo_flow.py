"""End-to-end demo flow: candidate resume -> OCR parse -> AI score -> HR pipeline.

Simulates the complete journey for the sample candidates by attaching the
generated resume PDFs to their applications, running OCR parsing + evaluation,
and advancing an application through the HR status pipeline.
"""

import os
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.files import File

from portal.models import CandidatePortalUser
from recruitment.models import Application, Candidate, Resume


class Command(BaseCommand):
    help = "Run the E2E demo: attach resumes, parse, score, and advance an application"

    def handle(self, *args, **options):
        sample_dir = os.path.join(settings.MEDIA_ROOT, "sample_resumes")

        # 1. Attach resumes to sample candidates
        portal_users = CandidatePortalUser.objects.filter(
            email__in=[
                "rahul.sharma@example.com",
                "sneha.reddy@example.com",
                "arjun.patel@example.com",
                "priya.sharma@example.com",
                "vikram.singh@example.com",
            ]
        )

        attached = 0
        for pu in portal_users:
            cand = Candidate.objects.filter(portal_user=pu).first()
            if not cand:
                continue
            pdf = os.path.join(sample_dir, f"resume_{pu.email.split('@')[0]}.pdf")
            if not os.path.exists(pdf):
                continue
            if cand.resumes.exists():
                continue
            with open(pdf, "rb") as fh:
                Resume.objects.create(candidate=cand, file=File(fh, name=os.path.basename(pdf)))
            attached += 1

        self.stdout.write(self.style.SUCCESS(f"Attached {attached} resumes. "
                                             "Resume post_save signal triggered OCR parse + AI evaluation."))

        # 2. Report scores
        scored = Application.objects.exclude(resume_score=0)
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== AI Resume Scores ==="))
        for app in scored.order_by("-resume_score"):
            self.stdout.write(
                f"  {app.application_id}: {app.candidate} — {app.post.name} — "
                f"{app.resume_score}/100"
            )

        # 3. Advance one application to "shortlisted" to show HR pipeline
        best = scored.order_by("-resume_score").first()
        if best:
            if best.status == "received":
                best.status = "document_verification"
                best.save()
            self.stdout.write(self.style.MIGRATE_HEADING("\n=== HR Pipeline Demo ==="))
            self.stdout.write(
                f"  {best.application_id} ({best.candidate}) advanced to '{best.status}'. "
                f"HR can now run eligibility, allocate category, schedule interview."
            )

        self.stdout.write(self.style.SUCCESS("\nE2E flow complete."))
        self.stdout.write(self.style.WARNING(
            "Open the HR dashboard to see scores: http://neepco.localhost:8000/ "
            "and the candidate portal to see resume status."
        ))
