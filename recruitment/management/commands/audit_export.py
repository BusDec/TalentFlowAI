"""Export the immutable application audit trail as CSV.

Usage:
    python manage.py audit_export
    python manage.py audit_export --output audit.csv --application TF20260001 --limit 100
"""

import csv

from django.core.management.base import BaseCommand

from recruitment.models import AuditEvent

CSV_HEADER = [
    "timestamp",
    "actor",
    "tenant_schema",
    "application",
    "field_name",
    "old_value",
    "new_value",
    "reason",
]


class Command(BaseCommand):
    help = "Export the immutable application audit trail as CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            "-o",
            dest="output",
            help="Write CSV to this file instead of stdout.",
        )
        parser.add_argument(
            "--application",
            dest="application_id",
            help="Only export events for this application_id.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            dest="limit",
            default=None,
            help="Maximum number of rows to export.",
        )

    def handle(self, *args, **options):
        queryset = AuditEvent.objects.all()
        if options["application_id"]:
            queryset = queryset.filter(application__application_id=options["application_id"])
        if options["limit"]:
            queryset = queryset[: options["limit"]]

        if options["output"]:
            with open(options["output"], "w", newline="", encoding="utf-8") as fh:
                self._write_csv(fh, queryset)
            self.stdout.write(self.style.SUCCESS(f"Audit trail written to {options['output']}"))
        else:
            self._write_csv(self.stdout, queryset)

    @staticmethod
    def _write_csv(stream, queryset):
        writer = csv.writer(stream)
        writer.writerow(CSV_HEADER)
        for event in queryset.iterator():
            writer.writerow(
                [
                    event.timestamp.isoformat(),
                    event.actor.username if event.actor else "",
                    event.tenant_schema,
                    event.application.application_id if event.application else "",
                    event.field_name,
                    event.old_value,
                    event.new_value,
                    event.reason,
                ]
            )
