"""Simulate roster matrices and panel lists for NEEPCO posts."""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q

from recruitment.models import Application, CategoryAllocation, PanelList, Post, RosterMatrix


class Command(BaseCommand):
    help = "Simulate RosterMatrix + PanelList for Phase I posts"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting roster & panel simulation..."))

        posts = Post.objects.all()
        if not posts.exists():
            self.stdout.write(self.style.WARNING("No posts found. Run simulate_neepco_advt first."))
            return

        categories = [
            ("ur", 40), ("obc", 27), ("sc", 15), ("st", 7.5), ("ews", 10),
        ]
        created_matrix = 0
        created_panel = 0

        for post in posts:
            # Create a weighted category matrix proportional to post vacancies.
            for cat, weight in categories:
                slots = max(0, round(post.vacancies * weight / 100))
                if cat == "ur" and slots == 0:
                    slots = max(1, post.vacancies - 1)
                RosterMatrix.objects.get_or_create(
                    post=post,
                    category=cat,
                    defaults={
                        "vertical_vacancies": slots,
                        "pwbd_horizontal_vacancies": 1 if post.vacancies >= 3 else 0,
                        "carry_forward": random.choice([True, False]),
                    },
                )
                created_matrix += 1

            # Allocate categories to some applications.
            apps = post.applications.filter(
                Q(status__in=["shortlisted", "interview", "offered", "joined"])
            )[: post.vacancies + 3]
            cat_cycle = ["ur", "obc", "sc", "st", "ews"]
            for idx, app in enumerate(apps):
                CategoryAllocation.objects.get_or_create(
                    application=app,
                    category=cat_cycle[idx % len(cat_cycle)],
                    defaults={
                        "is_verified": True,
                        "fills_slot": idx < post.vacancies,
                    },
                )

            # Build a small panel list from remaining applications.
            panel_pool = (
                post.applications.exclude(status__in=["rejected", "withdrawn"])
                .exclude(id__in=[a.id for a in apps])
            )[:4]
            for rank, app in enumerate(panel_pool, start=1):
                _, created = PanelList.objects.get_or_create(
                    post=post,
                    application=app,
                    defaults={
                        "panel_rank": rank,
                        "valid_until": date.today() + timedelta(days=365),
                        "is_active": True,
                    },
                )
                if created:
                    created_panel += 1

        self.stdout.write(self.style.SUCCESS(
            f"Simulation complete. Roster rows: {created_matrix}, panel entries: {created_panel}."
        ))
