"""Export the immutable application audit trail as CSV.

AuditEvent rows live in tenant schemas (recruitment is a tenant app), so this
command runs inside each tenant schema. With no --schema it aggregates every
tenant's events into one CSV (the tenant_schema column identifies the source).

Usage:
    python manage.py audit_export
    python manage.py audit_export --schema neepco
    python manage.py audit_export --output audit.csv --application TF20260001 --limit 100
"""

import csv

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, schema_context, schema_exists

from recruitment.models import AuditEvent
from tenants.models import Client

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
            "--schema",
            dest="schema",
            default=None,
            help="Tenant schema to export (default: all tenant schemas).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            dest="limit",
            default=None,
            help="Maximum number of rows to export (across all schemas).",
        )

    def handle(self, *args, **options):
        if options["schema"]:
            if not schema_exists(options["schema"]):
                raise CommandError(f"Schema '{options['schema']}' does not exist.")
            schemas = [options["schema"]]
        else:
            schemas = list(
                Client.objects.exclude(schema_name=get_public_schema_name())
                .values_list("schema_name", flat=True)
            )
            if not schemas:
                raise CommandError("No tenants found — nothing to export.")

        out = open(options["output"], "w", newline="", encoding="utf-8") if options["output"] else self.stdout
        try:
            writer = csv.writer(out)
            writer.writerow(CSV_HEADER)
            rows_written = 0
            limit = options["limit"]
            application_id = options["application_id"]
            for schema in schemas:
                with schema_context(schema):
                    queryset = AuditEvent.objects.all().order_by("-timestamp")
                    if application_id:
                        queryset = queryset.filter(
                            application__application_id=application_id
                        )
                    if limit and rows_written >= limit:
                        break
                    if limit:
                        queryset = queryset[: limit - rows_written]
                    # Plain iteration: QuerySet.iterator() uses named server-side
                    # cursors, which break when the search_path is switched
                    # between schemas mid-export.
                    for event in queryset:
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
                        rows_written += 1
        finally:
            if options["output"]:
                out.close()

        if options["output"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Audit trail written to {options['output']} ({rows_written} rows)."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"{rows_written} rows exported."))
