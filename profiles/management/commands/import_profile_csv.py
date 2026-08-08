"""Import candidate profiles from a TalentBridge-format CSV.

Run against a tenant schema:
    python manage.py tenant_command import_profile_csv --schema=neepco --file=path/to/candidates.csv
"""

from django.core.management.base import BaseCommand, CommandError

from profiles.importer import import_bio_csv


class Command(BaseCommand):
    help = "Import candidate profiles from a TalentBridge CANDIDATE_BIO CSV."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to the CSV file.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the file without writing anything.",
        )

    def handle(self, *args, **options):
        path = options["file"]
        try:
            with open(path, "rb") as fh:
                stats = import_bio_csv(fh, dry_run=options["dry_run"])
        except FileNotFoundError:
            raise CommandError(f"File not found: {path}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Rows: {stats['rows']} | created: {stats['created']} | "
                f"updated: {stats['updated']} | skipped (no email): {stats['skipped']}"
                + (" (dry-run)" if options["dry_run"] else "")
            )
        )
