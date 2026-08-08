"""Simulate the NEEPCO/02/2026 advertisement (Phase I recruitment)."""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from recruitment.models import (
    Advertisement,
    Application,
    BackgroundReport,
    Candidate,
    Post,
)


class Command(BaseCommand):
    help = "Simulate NEEPCO Advertisement No. NEEPCO/02/2026 with sample data"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting simulation of NEEPCO/02/2026..."))

        advt, created = Advertisement.objects.get_or_create(
            advt_number="NEEPCO/02/2026",
            defaults={
                "title": "Recruitment of Executives on Fixed Term Basis",
                "description": (
                    "Fixed Term Executives across multiple disciplines "
                    "(Civil, Finance, ERP, Medical, Safety, Security, Law, CSR, "
                    "Corporate Communication)."
                ),
                "published_date": date(2026, 6, 23),
                "closing_date": date(2026, 7, 13),
                "is_active": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created Advertisement: {advt}"))
        else:
            self.stdout.write(self.style.WARNING(f"Advertisement already exists: {advt}"))

        posts_data = [
            {"name": "Executive (ERP)", "post_code": "FTB/5/HR/49", "vacancies": 2, "max_age": 37,
             "qualification": "BE/B.Tech + SAP HCM certification", "pay_scale": "Rs 1,66,000"},
            {"name": "Executive (HR - Corporate Communication)", "post_code": "FTB/5/HR/173", "vacancies": 1, "max_age": 37,
             "qualification": "Graduate + PG in Mass Communication/Journalism", "pay_scale": "Rs 1,66,000"},
            {"name": "Executive (Civil) - Senior", "post_code": "FTB/5/HR/12", "vacancies": 3, "max_age": 37,
             "qualification": "B.Tech Civil + relevant experience", "pay_scale": "Rs 1,66,000"},
            {"name": "Executive (Civil)", "post_code": "FTB/4/HR/13", "vacancies": 3, "max_age": 34,
             "qualification": "B.Tech Civil", "pay_scale": "Rs 1,45,000"},
            {"name": "Executive (Civil) - Junior", "post_code": "FTB/1/HR/21", "vacancies": 3, "max_age": 30,
             "qualification": "B.Tech Civil", "pay_scale": "Rs 71,000"},
            {"name": "Executive (Security)", "post_code": "FTB/SEC/01", "vacancies": 4, "max_age": 37,
             "qualification": "Graduate + relevant experience", "pay_scale": "Rs 1,45,000"},
            {"name": "Executive (Law)", "post_code": "FTB/LAW/01", "vacancies": 1, "max_age": 37,
             "qualification": "LLB", "pay_scale": "Rs 1,45,000"},
            {"name": "Executive (Safety)", "post_code": "FTB/SAF/01", "vacancies": 2, "max_age": 37,
             "qualification": "Engineering + Safety qualification", "pay_scale": "Rs 1,45,000"},
            {"name": "Executive (Finance) - Experienced", "post_code": "FTB/4/HR/257", "vacancies": 6, "max_age": 34,
             "qualification": "CA/CMA/MBA Finance + 4 years experience", "pay_scale": "Rs 1,45,000"},
            {"name": "Executive (Finance)", "post_code": "FTB/2/HR/256", "vacancies": 6, "max_age": 30,
             "qualification": "CA/CMA/MBA Finance", "pay_scale": "Rs 90,000"},
            {"name": "Executive (Medical)", "post_code": "FTB/MED/01", "vacancies": 5, "max_age": 37,
             "qualification": "MBBS", "pay_scale": "Rs 1,35,000"},
            {"name": "Executive (HR - CSR)", "post_code": "FTB/CSR/01", "vacancies": 2, "max_age": 34,
             "qualification": "MSW / relevant PG", "pay_scale": "Rs 90,000"},
        ]

        created_posts = []
        for data in posts_data:
            post, created = Post.objects.get_or_create(
                advertisement=advt,
                post_code=data["post_code"],
                defaults={
                    "name": data["name"],
                    "vacancies": data["vacancies"],
                    "max_age": data["max_age"],
                    "qualification": data["qualification"],
                    "experience_required": "As per advertisement",
                    "pay_scale": data["pay_scale"],
                },
            )
            created_posts.append(post)
            if created:
                self.stdout.write(f"  -> Created Post: {post.name}")

        first_names = [
            "Rahul", "Priya", "Amit", "Sneha", "Vikram", "Neha", "Arjun", "Meera",
            "Karan", "Divya", "Rohit", "Ananya", "Rajesh", "Sunita", "Ankit",
            "Kavita", "Siddharth", "Pooja",
        ]
        last_names = ["Sharma", "Patel", "Singh", "Reddy", "Verma", "Gupta", "Nair",
                      "Joshi", "Mehta", "Das"]

        statuses = ["received", "document_verification", "shortlisted", "interview",
                    "offered", "joined", "rejected"]
        status_weights = [20, 25, 20, 15, 8, 5, 7]

        total_apps = 0
        for post in created_posts:
            num_apps = random.randint(5, 9)
            for i in range(num_apps):
                first = random.choice(first_names)
                last = random.choice(last_names)
                email = f"{first.lower()}.{last.lower()}{random.randint(10, 99)}@example.com"

                candidate, _ = Candidate.objects.get_or_create(
                    email=email,
                    defaults={
                        "first_name": first,
                        "last_name": last,
                        "mobile": f"98{random.randint(10000000, 99999999)}",
                        "date_of_birth": date(1990, 1, 1) + timedelta(days=random.randint(0, 5000)),
                    },
                )

                application_id = f"{post.post_code.split('/')[-1]}-{2026}-{100 + total_apps}"
                status = random.choices(statuses, weights=status_weights, k=1)[0]

                application, created = Application.objects.get_or_create(
                    post=post,
                    candidate=candidate,
                    defaults={
                        "application_id": application_id,
                        "status": status,
                    },
                )

                if created:
                    total_apps += 1
                    BackgroundReport.objects.get_or_create(
                        application=application,
                        defaults={
                            "facts": {
                                "disclaimer": (
                                    "These are compiled facts only. No automated decision has been made."
                                ),
                                "rows": [
                                    {
                                        "category": "Identity",
                                        "fact": f"{candidate.first_name} {candidate.last_name}",
                                        "source": "Application form",
                                        "status": "declared",
                                        "candidate_explanation": "",
                                        "reviewer_notes": "",
                                    },
                                    {
                                        "category": "Court Records",
                                        "fact": random.choice(
                                            ["No record found in searched jurisdictions.",
                                             "One disposed case (2019) — acquitted."]
                                        ),
                                        "source": "Licensed BGV provider",
                                        "status": random.choice(["clear", "disposed"]),
                                        "candidate_explanation": "",
                                        "reviewer_notes": "",
                                    },
                                ],
                            },
                            "status": random.choice(["pending", "explained", "reviewed"]),
                        },
                    )

        self.stdout.write(self.style.SUCCESS(
            f"\nSuccessfully created {total_apps} sample applications across {len(created_posts)} posts."
        ))
        self.stdout.write(self.style.SUCCESS("Simulation of NEEPCO/02/2026 completed."))
