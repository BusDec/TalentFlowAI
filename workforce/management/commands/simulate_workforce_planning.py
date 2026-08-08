"""Simulate Workforce Planning data (Phase II)."""

from datetime import date

from django.core.management.base import BaseCommand

from workforce.models import ManpowerRequirement, RecruitmentBatch, RetirementForecast


class Command(BaseCommand):
    help = "Simulate workforce planning (retirement + requirement + batches) for next 7 years"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting Phase II – Workforce Planning simulation..."))

        retirement_data = [
            {"year": 2026, "executives": 52, "supervisors": 20, "workmen": 42},
            {"year": 2027, "executives": 48, "supervisors": 16, "workmen": 48},
            {"year": 2028, "executives": 45, "supervisors": 15, "workmen": 55},
            {"year": 2029, "executives": 38, "supervisors": 14, "workmen": 50},
            {"year": 2030, "executives": 32, "supervisors": 12, "workmen": 45},
            {"year": 2031, "executives": 28, "supervisors": 11, "workmen": 40},
            {"year": 2032, "executives": 25, "supervisors": 10, "workmen": 35},
        ]

        for item in retirement_data:
            total = item["executives"] + item["supervisors"] + item["workmen"]
            obj, created = RetirementForecast.objects.update_or_create(
                year=item["year"],
                defaults={
                    "executives": item["executives"],
                    "supervisors": item["supervisors"],
                    "workmen": item["workmen"],
                    "total": total,
                    "notes": "Simulated from historical age profile + attrition",
                },
            )
            self.stdout.write(f"  -> RetirementForecast {item['year']}: {total} ({'created' if created else 'updated'})")

        requirement_data = [
            {
                "start": date(2026, 4, 1), "end": date(2028, 3, 31),
                "exec": 145, "sup": 45, "wm": 90,
                "drivers": "Heo + Tato-I construction peak + heavy retirements",
            },
            {
                "start": date(2028, 4, 1), "end": date(2030, 3, 31),
                "exec": 110, "sup": 35, "wm": 70,
                "drivers": "Tato-II ramp-up + commissioning support",
            },
            {
                "start": date(2030, 4, 1), "end": date(2033, 3, 31),
                "exec": 75, "sup": 25, "wm": 50,
                "drivers": "Stabilisation of new capacity + residual retirements",
            },
        ]

        for item in requirement_data:
            total = item["exec"] + item["sup"] + item["wm"]
            obj, created = ManpowerRequirement.objects.update_or_create(
                period_start=item["start"],
                period_end=item["end"],
                defaults={
                    "executives": item["exec"],
                    "supervisors": item["sup"],
                    "workmen": item["wm"],
                    "total": total,
                    "primary_drivers": item["drivers"],
                },
            )
            self.stdout.write(f"  -> ManpowerRequirement {total} ({item['start']} to {item['end']})")

        batches = [
            {
                "name": "Batch 1 - Critical (2026)",
                "adv_start": date(2026, 9, 1), "adv_end": date(2026, 10, 31),
                "target": 95, "join_start": date(2027, 6, 1), "join_end": date(2027, 8, 31),
                "purpose": "Cover 2027-28 retirements + Heo/Tato-I construction peak",
            },
            {
                "name": "Batch 2 - Tato-II Ramp-up",
                "adv_start": date(2027, 3, 1), "adv_end": date(2027, 4, 30),
                "target": 75, "join_start": date(2028, 1, 1), "join_end": date(2028, 3, 31),
                "purpose": "Tato-II manpower + continued retirements",
            },
            {
                "name": "Batch 3 - Commissioning Support",
                "adv_start": date(2027, 10, 1), "adv_end": date(2027, 11, 30),
                "target": 65, "join_start": date(2028, 7, 1), "join_end": date(2028, 9, 30),
                "purpose": "Commissioning of Heo & Tato-I",
            },
        ]

        for b in batches:
            obj, created = RecruitmentBatch.objects.update_or_create(
                name=b["name"],
                defaults={
                    "advertisement_window_start": b["adv_start"],
                    "advertisement_window_end": b["adv_end"],
                    "target_posts": b["target"],
                    "expected_joining_start": b["join_start"],
                    "expected_joining_end": b["join_end"],
                    "purpose": b["purpose"],
                    "is_approved": False,
                },
            )
            self.stdout.write(f"  -> RecruitmentBatch: {b['name']}")

        self.stdout.write(self.style.SUCCESS("Phase II simulation completed."))
