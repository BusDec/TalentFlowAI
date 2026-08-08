"""Simulate internal job postings + employee applications."""

import random
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from recruitment.models import InternalApplication, InternalJobPosting

User = get_user_model()


class Command(BaseCommand):
    help = "Simulate internal job postings and employee applications"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting internal posting simulation..."))

        postings_data = [
            {
                "title": "Lead Engineer — Pumped Storage (Internal)",
                "grade": "E6-E7",
                "min_exp": 8,
                "deputation": True,
                "priority": "high",
            },
            {
                "title": "Project Manager — Hydro Construction",
                "grade": "E8",
                "min_exp": 12,
                "deputation": True,
                "priority": "critical",
            },
            {
                "title": "Digital Transformation Officer",
                "grade": "E4-E5",
                "min_exp": 5,
                "deputation": False,
                "priority": "normal",
            },
        ]

        for data in postings_data:
            InternalJobPosting.objects.get_or_create(
                title=data["title"],
                defaults={
                    "description": f"Internal posting for {data['title']}.",
                    "grade": data["grade"],
                    "min_experience_years": data["min_exp"],
                    "deputation_eligible": data["deputation"],
                    "priority_flag": data["priority"],
                    "open_from": date.today(),
                    "open_until": date.today() + timedelta(days=30),
                    "is_active": True,
                },
            )

        employees = list(User.objects.filter(is_staff=True, is_superuser=False)) or \
            list(User.objects.filter(is_superuser=False))
        if not employees:
            self.stdout.write(self.style.WARNING("No employees found to apply. Skipping applications."))

        applied = 0
        for posting in InternalJobPosting.objects.all():
            for emp in random.sample(employees, k=min(3, len(employees))) if employees else []:
                _, created = InternalApplication.objects.get_or_create(
                    posting=posting,
                    applicant=emp,
                    defaults={
                        "status": random.choice(["applied", "shortlisted"]),
                        "current_grade": random.choice(["E4", "E5", "E6", "E7"]),
                        "years_at_org": random.randint(4, 15),
                    },
                )
                if created:
                    applied += 1

        self.stdout.write(self.style.SUCCESS(
            f"Simulation complete. Postings: {InternalJobPosting.objects.count()}, applications: {applied}."
        ))
