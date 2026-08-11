"""Seed realistic NEEPCO test data for cloud deployment.

Idempotent — safe to run on every startup. Creates:
  - Active advertisement (NEEPCO/02/2026) with 12 real posts
  - Sample candidates with Indian names
  - Applications in various workflow stages
  - All data from the actual NEEPCO advertisement PDF
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import connection

from recruitment.models import (
    Advertisement,
    Application,
    Candidate,
    Post,
)


# ── Real NEEPCO post details from the official advertisement ──────────────────

NEEPCO_POSTS = [
    {
        "post_code": "FTB/5/HR/49",
        "name": "Executive (HR)",
        "vacancies": 2, "max_age": 37,
        "category": {"ur": 2},
        "qualification": "MBA/PGDM in HR/Personnel Management (2 yrs full time) from a recognized University/Institute.",
        "experience": "Minimum 7 years post-qualification experience in HR function in a CPSU/large organization.",
        "pay_scale": "Rs 1,66,000/-",
    },
    {
        "post_code": "FTB/5/HR/173",
        "name": "Executive (HR) (Corporate Communication)",
        "vacancies": 1, "max_age": 37,
        "category": {"ur": 1},
        "qualification": "Graduate with PG Degree/Diploma in Mass Communication/Journalism (2 yrs full time).",
        "experience": "Minimum 7 years in public relations/corporate communication, media planning, content creation.",
        "pay_scale": "Rs 1,66,000/-",
    },
    {
        "post_code": "FTB/5/HR/12",
        "name": "Executive (Civil)",
        "vacancies": 3, "max_age": 37,
        "category": {"ur": 3},
        "qualification": "Full time Bachelor Degree in Civil Engineering from a recognized University/Institute.",
        "experience": "7 years post-qualification experience in civil construction of Hydropower projects.",
        "pay_scale": "Rs 1,66,000/-",
    },
    {
        "post_code": "FTB/4/HR/13",
        "name": "Executive (Civil)",
        "vacancies": 3, "max_age": 34,
        "category": {"ur": 2, "obc": 1},
        "qualification": "Full time Bachelor Degree in Civil Engineering from a recognized University/Institute.",
        "experience": "4 years post-qualification experience in Hydropower projects.",
        "pay_scale": "Rs 1,45,000/-",
    },
    {
        "post_code": "FTB/1/HR/21",
        "name": "Executive (Civil)",
        "vacancies": 3, "max_age": 30,
        "category": {"ur": 1, "sc": 1, "obc": 1},
        "qualification": "Bachelor Degree/3 years Diploma in Civil Engineering.",
        "experience": "1 year (degree) or 5 years (diploma) in Survey & Investigation of hydro power projects.",
        "pay_scale": "Rs 71,000/-",
    },
    {
        "post_code": "FTB/4/HR/291",
        "name": "Executive (Security)",
        "vacancies": 4, "max_age": 34,
        "category": {"ur": 2, "sc": 1, "obc": 1},
        "qualification": "Graduate in any discipline recognized by Govt. of India.",
        "experience": "9 years in Armed Forces (Captain/Major/Lt Col) or DSP/SP equivalent in Police.",
        "pay_scale": "Rs 1,45,000/-",
    },
    {
        "post_code": "FTB/4/HR/183",
        "name": "Executive (Law)",
        "vacancies": 1, "max_age": 34,
        "category": {"ur": 1},
        "qualification": "Bachelor's Degree in Law (LLB) full time from recognized University.",
        "experience": "6 years practice in Court of Law or 9 years in CPSU/GOI.",
        "pay_scale": "Rs 1,45,000/-",
    },
    {
        "post_code": "FTB/4/HR/83",
        "name": "Executive (Safety)",
        "vacancies": 2, "max_age": 34,
        "category": {"ur": 2},
        "qualification": "Engineering Degree in Mechanical/Electrical/Production with Diploma in Industrial Safety.",
        "experience": "4 years in compliance with safety regulations under the Factories Act.",
        "pay_scale": "Rs 1,45,000/-",
    },
    {
        "post_code": "FTB/4/HR/257",
        "name": "Executive (Finance)",
        "vacancies": 6, "max_age": 34,
        "category": {"ur": 5, "obc": 1},
        "qualification": "Graduate with CA/CMA or MBA (Finance) of at least 2 years duration.",
        "experience": "Minimum 4 years in the relevant field.",
        "pay_scale": "Rs 1,45,000/-",
    },
    {
        "post_code": "FTB/2/HR/256",
        "name": "Executive (Finance)",
        "vacancies": 6, "max_age": 30,
        "category": {"ur": 2, "sc": 1, "obc": 2, "ews": 1},
        "qualification": "Graduate with CA/CMA or MBA (Finance) of at least 2 years duration.",
        "experience": "As per advertisement.",
        "pay_scale": "Rs 90,000/-",
    },
    {
        "post_code": "FTB/3/HR/280",
        "name": "Executive (Medical)",
        "vacancies": 5, "max_age": 31,
        "category": {"ur": 4, "obc": 1},
        "qualification": "MBBS preferably with PG Degree/Diploma, registered with Indian Medical Council.",
        "experience": "1 year in large industry/reputed hospital after internship.",
        "pay_scale": "Rs 1,35,000/-",
    },
    {
        "post_code": "FTB/2/HR/159",
        "name": "Executive (HR) (CSR)",
        "vacancies": 2, "max_age": 30,
        "category": {"ur": 2},
        "qualification": "Master's Degree in Social Work / Community Organisation recognized by GOI.",
        "experience": "1 year in CSR/Social Welfare works in a reputed organization.",
        "pay_scale": "Rs 90,000/-",
    },
]

NEEPCO_PROFILE = (
    "North Eastern Electric Power Corporation Limited, (an equal opportunity employer) "
    "a Schedule 'A' Mini Ratna CPSE and a Wholly Owned Subsidiary of NTPC, has been a "
    "trusted power generation Company in the North Eastern Region of India since 1976."
)

# Sample candidate names (Indian, diverse)
FIRST_NAMES_M = ["Amit", "Rahul", "Vijay", "Sanjay", "Arjun", "Deepak", "Rohan", "Kiran", "Nikhil", "Saurabh",
                 "Pranab", "Manoj", "Rajesh", "Ashish", "Pankaj", "Gaurav", "Vikram", "Ankit", "Tarun", "Nitesh"]
FIRST_NAMES_F = ["Priya", "Sunita", "Ananya", "Kavita", "Neha", "Ritu", "Pooja", "Swati", "Meera", "Divya",
                 "Shruti", "Nandini", "Aparna", "Jyoti", "Rekha", "Sushma", "Kabita", "Lata", "Anita", "Deepa"]
LAST_NAMES = ["Sharma", "Patel", "Singh", "Reddy", "Verma", "Gupta", "Nair", "Joshi", "Mehta", "Das",
              "Kumar", "Rao", "Mishra", "Choudhury", "Borah", "Hazarika", "Gogoi", "Saikia", "Debbarma", "Brahma"]
STATUSES = ["received", "document_verification", "shortlisted", "interview", "offered", "joined", "rejected"]
STATUS_WEIGHTS = [20, 25, 20, 15, 8, 5, 7]


class Command(BaseCommand):
    help = "Seed NEEPCO test data (advertisement, posts, candidates, applications). Idempotent."

    def handle(self, *args, **options):
        # Run inside the neepco tenant schema
        connection.set_schema_to_public()
        from tenants.models import Client

        try:
            tenant = Client.objects.get(schema_name="neepco")
        except Client.DoesNotExist:
            self.stdout.write(self.style.ERROR("  neepco tenant not found. Run setup_tenant first."))
            return

        from django_tenants.utils import schema_context

        with schema_context("neepco"):
            self._seed()

    def _seed(self):
        # ── Advertisement ─────────────────────────────────────────────────────
        advt, advt_created = Advertisement.objects.get_or_create(
            advt_number="NEEPCO/02/2026",
            defaults={
                "title": "Recruitment of Executives in various disciplines",
                "description": NEEPCO_PROFILE,
                "published_date": date(2026, 6, 15),
                "closing_date": date(2026, 9, 30),
                "is_active": True,
                "health_text": "Must be in good mental and bodily health and free from any bodily defect likely to interfere with the efficient performance of duties.",
                "how_to_apply": "Apply online through the NEEPCO recruitment portal before the closing date.",
                "general_conditions": "All posts are transferable anywhere in India. Age relaxation as per Govt. of India norms.",
            },
        )
        if advt_created:
            self.stdout.write(self.style.SUCCESS(f"  Created advertisement: {advt.advt_number}"))
        else:
            self.stdout.write(f"  Advertisement exists: {advt.advt_number}")

        # ── Posts ──────────────────────────────────────────────────────────────
        posts = []
        for pd in NEEPCO_POSTS:
            post, p_created = Post.objects.get_or_create(
                advertisement=advt,
                post_code=pd["post_code"],
                defaults={
                    "name": pd["name"],
                    "vacancies": pd["vacancies"],
                    "max_age": pd["max_age"],
                    "qualification": pd["qualification"],
                    "experience_required": pd["experience"],
                    "pay_scale": pd["pay_scale"],
                    "category_breakup": pd["category"],
                    "location": "Shillong or any Offices/Project sites of NEEPCO, anywhere in India",
                    "period_of_engagement": "Initially for 3 years extendable by 2 years based on performance",
                    "age_cutoff_date": advt.closing_date,
                    "min_education_level": "graduate",
                },
            )
            posts.append(post)
            if p_created:
                self.stdout.write(f"    Post: {post.post_code} — {post.name}")

        # ── Skip candidates + applications if they already exist ──────────────
        if Application.objects.exists():
            total = Application.objects.count()
            self.stdout.write(f"  {total} applications already exist — skipping seed.")
            return

        # ── Candidates ────────────────────────────────────────────────────────
        candidates = []
        for i in range(60):
            gender = random.choice(["M", "F"])
            fn = random.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
            ln = random.choice(LAST_NAMES)
            c = Candidate.objects.create(
                first_name=fn,
                last_name=ln,
                email=f"{fn.lower()}.{ln.lower()}{i}@gmail.com",
                mobile=f"9{random.randint(100000000, 999999999)}",
                date_of_birth=date(1990, 1, 1) + timedelta(days=random.randint(0, 365 * 10)),
            )
            candidates.append(c)

        self.stdout.write(self.style.SUCCESS(f"  Created {len(candidates)} candidates"))

        # ── Applications ──────────────────────────────────────────────────────
        total_apps = 0
        for post in posts:
            num_apps = random.randint(5, 12)
            chosen = random.sample(candidates, min(num_apps, len(candidates)))
            for idx, cand in enumerate(chosen):
                if Application.objects.filter(post=post, candidate=cand).exists():
                    continue
                status = random.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
                app_id = f"NEEPCO-{post.post_code.split('/')[-1]}-{cand.pk:04d}"
                Application.objects.create(
                    post=post,
                    candidate=cand,
                    application_id=app_id,
                    status=status,
                    resume_score=random.randint(30, 95),
                )
                total_apps += 1

        self.stdout.write(self.style.SUCCESS(
            f"  Created {total_apps} applications across {len(posts)} posts"
        ))
        self.stdout.write(self.style.SUCCESS("Seed data complete."))
