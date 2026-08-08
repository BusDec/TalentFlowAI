"""Generate sample resume PDFs for the demo candidates.

Creates realistic, OCR-able text-based resumes in the media/resumes/ folder.
These can be uploaded via the candidate portal to test the full pipeline:
resume upload -> OCR parse -> AI evaluation -> HR review.
"""

import os
import random
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand
from fpdf import FPDF


class Command(BaseCommand):
    help = "Generate sample resume PDFs for demo candidates"

    def handle(self, *args, **options):
        from portal.models import CandidatePortalUser
        from recruitment.models import Candidate

        out_dir = os.path.join(settings.MEDIA_ROOT, "sample_resumes")
        os.makedirs(out_dir, exist_ok=True)

        portal_users = CandidatePortalUser.objects.filter(
            email__in=[
                "rahul.sharma@example.com",
                "sneha.reddy@example.com",
                "arjun.patel@example.com",
                "priya.sharma@example.com",
                "vikram.singh@example.com",
            ]
        )

        profiles = self._build_profiles()
        created = 0
        for pu in portal_users:
            profile = profiles.get(pu.email)
            if not profile:
                continue
            # Prefer the candidate's real name; fall back to portal full_name.
            cand = Candidate.objects.filter(portal_user=pu).first()
            name = cand and f"{cand.first_name} {cand.last_name}".strip() or pu.full_name or pu.email
            filepath = os.path.join(out_dir, f"resume_{pu.email.split('@')[0]}.pdf")
            self._write_pdf(filepath, name, profile)
            created += 1
            self.stdout.write(f"  -> {filepath}")

        self.stdout.write(self.style.SUCCESS(f"Generated {created} sample resumes in {out_dir}"))
        self.stdout.write(self.style.WARNING(
            "Upload them via the candidate portal (/portal/login/ then apply -> Upload Resume)."
        ))

    def _build_profiles(self):
        return {
            "rahul.sharma@example.com": {
                "phone": "9811100001",
                "email": "rahul.sharma@example.com",
                "dob": "15-03-1992",
                "degree": "B.Tech Civil Engineering",
                "university": "IIT Guwahati",
                "year": 2014,
                "percentage": "78.4%",
                "experience": 7,
                "designation": "Assistant Manager (Civil)",
                "org": "THDC India Limited",
                "skills": "SAP S/4HANA, AutoCAD, Primavera P6, MS Project, FIDIC, Survey & Investigation",
                "summary": "7 years in hydro power project construction. Led DPR preparation for PSP projects. Strong in SAP and contract management.",
                "jobs": [
                    ("2019 - Present", "Assistant Manager (Civil)", "THDC India Limited", "Hydro power project construction, DPR preparation, contract management."),
                    ("2014 - 2019", "Engineer (Civil)", "Hydro Construct Pvt Ltd", "Survey & investigation, site supervision, quality control."),
                ],
            },
            "sneha.reddy@example.com": {
                "phone": "9811100002",
                "email": "sneha.reddy@example.com",
                "dob": "22-07-1994",
                "degree": "B.Tech Electrical Engineering",
                "university": "NIT Warangal",
                "year": 2016,
                "percentage": "72.1%",
                "experience": 4,
                "designation": "Engineer (Electrical)",
                "org": "Power Grid Corporation",
                "skills": "Substation Design, SCADA, Power Systems, AutoCAD Electrical, SAP",
                "summary": "4 years in transmission and substation projects. Experienced in O&M of 220kV substations.",
                "jobs": [
                    ("2020 - Present", "Engineer (Electrical)", "Power Grid Corporation", "O&M of 220kV substations, protection systems, SCADA."),
                    ("2016 - 2020", "Graduate Engineer Trainee", "Power Grid Corporation", "Substation commissioning and testing."),
                ],
            },
            "arjun.patel@example.com": {
                "phone": "9876543210",
                "email": "arjun.patel@example.com",
                "dob": "05-11-1989",
                "degree": "B.Com + CA (ICAI)",
                "university": "University of Delhi",
                "year": 2012,
                "percentage": "CA Qualified",
                "experience": 6,
                "designation": "Manager (Finance)",
                "org": "NHPC Limited",
                "skills": "Financial Modelling, SAP FI, Audit, Taxation, GST, Budgeting",
                "summary": "Chartered Accountant with 6 years in PSU finance, budgeting and project finance for hydro projects.",
                "jobs": [
                    ("2019 - Present", "Manager (Finance)", "NHPC Limited", "Budgeting, project finance, statutory audit coordination."),
                    ("2013 - 2019", "Senior Associate", "Deloitte India", "Statutory audit, tax advisory for power sector clients."),
                ],
            },
            "priya.sharma@example.com": {
                "phone": "9812345678",
                "email": "priya.sharma@example.com",
                "dob": "18-02-1993",
                "degree": "MBBS",
                "university": "AIIMS Delhi",
                "year": 2017,
                "percentage": "Distinction",
                "experience": 3,
                "designation": "Medical Officer",
                "org": "Fortis Hospital",
                "skills": "Emergency Medicine, Occupational Health, Critical Care, NABH Compliance",
                "summary": "MBBS doctor with 3 years in emergency and occupational health. Registered with Medical Council of India.",
                "jobs": [
                    ("2021 - Present", "Medical Officer", "Fortis Hospital", "Emergency medicine, occupational health checks."),
                    ("2018 - 2021", "Resident Medical Officer", "City Hospital", "Emergency and ICU duties."),
                ],
            },
            "vikram.singh@example.com": {
                "phone": "9811100005",
                "email": "vikram.singh@example.com",
                "dob": "10-09-1996",
                "degree": "Diploma in Civil Engineering",
                "university": "Government Polytechnic",
                "year": 2018,
                "percentage": "65.2%",
                "experience": 2,
                "designation": "Site Supervisor",
                "org": "Small Construction Co",
                "skills": "AutoCAD, Surveying, MS Office",
                "summary": "Diploma holder with 2 years of site supervision experience in residential construction.",
                "jobs": [
                    ("2022 - Present", "Site Supervisor", "Small Construction Co", "Site supervision, material management."),
                ],
            },
        }

    def _write_pdf(self, filepath, name, p):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 10, name, ln=True, align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, f"Email: {p['email']}  |  Phone: {p['phone']}  |  DOB: {p['dob']}", ln=True, align="C")
        pdf.ln(6)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "PROFESSIONAL SUMMARY", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, p["summary"])
        pdf.ln(3)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "EDUCATION", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(
            0, 6,
            f"{p['degree']} ({p['percentage']})\n{p['university']} - {p['year']}",
        )
        pdf.ln(3)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "WORK EXPERIENCE", ln=True)
        pdf.set_font("Helvetica", "", 10)
        for period, role, org, desc in p["jobs"]:
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, f"{role} | {org}", ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 6, period, ln=True)
            pdf.multi_cell(0, 6, desc)
            pdf.ln(2)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "SKILLS", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, p["skills"])
        pdf.output(filepath)
