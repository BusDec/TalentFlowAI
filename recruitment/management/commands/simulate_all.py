"""Master command — runs all Phase I/II/III simulations in sequence."""

from django.core.management import call_command
from django.core.management.base import BaseCommand

COMMANDS = [
    ("simulate_neepco_advt", "Phase I — Recruitment"),
    ("simulate_roster_panel", "Phase I — Roster & Panels"),
    ("simulate_duplicates_consents", "Phase I — Duplicates & Consents"),
    ("simulate_internal_posting", "Phase I — Internal Postings"),
    ("simulate_workforce_planning", "Phase II — Workforce Planning"),
    ("simulate_talent_data", "Phase III — Talent & L&D"),
]


class Command(BaseCommand):
    help = "Run all TalentFlow AI simulation commands in sequence"

    def handle(self, *args, **options):
        for command, label in COMMANDS:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n===== {label} ({command}) ====="))
            call_command(command, verbosity=1)
        self.stdout.write(self.style.SUCCESS("\nAll simulations completed."))
