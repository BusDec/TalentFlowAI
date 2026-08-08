"""HR-facing profile utilities (import from the TalentBridge template)."""

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.decorators import require_role
from .importer import import_bio_csv, import_workbook


@login_required
@require_role("hr_manager")
def import_csv(request):
    if request.method == "POST":
        dry_run = request.POST.get("dry_run") == "on"
        data_file = request.FILES.get("csv_file")
        if not data_file:
            messages.error(request, "Please choose a file.")
            return redirect("profile_import")

        name = (data_file.name or "").lower()
        try:
            if name.endswith(".xlsx"):
                stats = import_workbook(data_file)
                msg = (
                    f"Workbook import: {stats['created']} created, {stats['updated']} updated, "
                    f"{stats['skipped']} skipped. Academic rows: {stats['academic']}, "
                    f"work rows: {stats['work']}."
                )
                if dry_run:
                    msg += " (dry-run selected — workbooks are imported directly; re-upload to adjust.)"
                messages.success(request, msg)
            elif name.endswith(".csv") or name.endswith(".txt"):
                stats = import_bio_csv(data_file, dry_run=dry_run)
                messages.success(
                    request,
                    f"CSV import: {stats['created']} created, {stats['updated']} updated, "
                    f"{stats['skipped']} skipped (no email)."
                    + (" (dry-run — nothing saved)" if dry_run else ""),
                )
            else:
                messages.error(request, "Unsupported file type. Use .xlsx or .csv.")
        except (csv.Error, KeyError) as exc:
            messages.error(request, f"Could not parse file: {exc}")
        return redirect("profile_import")
    return render(request, "profiles/import.html")
