"""Simulate Phase III talent map and training needs data."""

import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from talent.models import EmployeeSkill, Skill, TrainingNeed

User = get_user_model()


class Command(BaseCommand):
    help = "Simulate Phase III talent map (skills) + training needs assessment"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting Phase III – Talent & L&D simulation..."))

        skills_data = [
            ("Pumped Storage Design & Operation", "Technical"),
            ("Dam Safety & Instrumentation", "Technical"),
            ("Hydro Project Execution", "Technical"),
            ("Tunnel & Underground Works", "Technical"),
            ("Digital Twin / Project Analytics", "Digital"),
            ("SCADA & Control Systems", "Technical"),
            ("Contract Management (FIDIC)", "Commercial"),
            ("Leadership in Complex Projects", "Leadership"),
            ("Cybersecurity Awareness", "Digital"),
            ("ESG & Sustainability", "Compliance"),
            ("Financial Modelling", "Finance"),
            ("SAP HCM", "HR/ERP"),
        ]

        skills = []
        for name, category in skills_data:
            skill, _ = Skill.objects.get_or_create(name=name, defaults={"category": category})
            skills.append(skill)

        users = list(User.objects.filter(is_superuser=False))[:15]
        if not users:
            self.stdout.write(self.style.WARNING("No non-superuser accounts found. Skipping skill assignment."))
        else:
            for user in users:
                for skill in random.sample(skills, k=random.randint(3, 6)):
                    EmployeeSkill.objects.update_or_create(
                        user=user,
                        skill=skill,
                        defaults={
                            "proficiency": round(random.uniform(1.5, 4.8), 1),
                            "verified": random.choice([True, False]),
                        },
                    )
            self.stdout.write(self.style.SUCCESS(f"Assigned skills to {len(users)} users."))

        training_needs = [
            {
                "title": "Advanced Pumped Storage & Dam Safety",
                "priority": "critical",
                "target_count": 42,
                "timeline": "Next 12 months",
                "description": "Critical for upcoming PSP projects and retirement wave in hydro experts.",
            },
            {
                "title": "Digital Twin & Project Analytics",
                "priority": "high",
                "target_count": 65,
                "timeline": "Next 18 months",
                "description": "To improve project monitoring and decision making.",
            },
            {
                "title": "Contract Management (Updated FIDIC)",
                "priority": "medium",
                "target_count": 38,
                "timeline": "2027",
                "description": "Required for major EPC packages.",
            },
            {
                "title": "Leadership in Complex Hydro Projects",
                "priority": "high",
                "target_count": 25,
                "timeline": "Next 15 months",
                "description": "Succession preparation for senior project roles.",
            },
            {
                "title": "Cybersecurity & OT Security Awareness",
                "priority": "high",
                "target_count": 80,
                "timeline": "Annual + refreshers",
                "description": "Mandatory for O&M and project teams.",
            },
        ]

        for item in training_needs:
            obj, created = TrainingNeed.objects.update_or_create(
                title=item["title"],
                defaults={
                    "description": item["description"],
                    "priority": item["priority"],
                    "target_count": item["target_count"],
                    "recommended_timeline": item["timeline"],
                },
            )
            self.stdout.write(f"  -> TrainingNeed: {item['title']} ({'created' if created else 'updated'})")

        self.stdout.write(self.style.SUCCESS("Phase III simulation completed."))
