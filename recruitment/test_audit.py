"""Tests for the immutable application audit trail (Phase 1.4)."""

import io

import django.contrib.admin
from django.core.management import call_command
from django.db import connection

import recruitment.admin  # noqa: F401  (register AuditEventAdmin on the admin site)
from recruitment.models import AuditEvent


def test_status_change_logs_event(application, staff_user):
    application.status = "shortlisted"
    application.save(audit_actor=staff_user)

    event = AuditEvent.objects.filter(application=application, field_name="status").get()
    assert event.old_value == "received"
    assert event.new_value == "shortlisted"
    assert event.actor == staff_user
    assert event.tenant_schema == "neepco"
    assert event.tenant_schema == connection.schema_name


def test_score_change_logs_event(application):
    application.resume_score = 75
    application.save()

    event = AuditEvent.objects.filter(application=application, field_name="resume_score").get()
    assert event.old_value == "0"
    assert event.new_value == "75"


def test_no_event_on_unchanged_save(application):
    assert AuditEvent.objects.count() == 0

    application.save()

    assert AuditEvent.objects.count() == 0


def test_audit_immutable_in_admin():
    model_admin = django.contrib.admin.site._registry[AuditEvent]
    assert model_admin.has_add_permission(None) is False
    assert model_admin.has_change_permission(None) is False
    assert model_admin.has_delete_permission(None) is False


def test_audit_export_command(application, staff_user):
    application.status = "shortlisted"
    application.save(audit_actor=staff_user)

    out = io.StringIO()
    call_command("audit_export", stdout=out)
    csv_text = out.getvalue()

    lines = csv_text.strip().splitlines()
    assert lines[0] == (
        "timestamp,actor,tenant_schema,application,field_name,old_value,new_value,reason"
    )
    assert any(",staff1,neepco,TF20260001,status,received,shortlisted," in line for line in lines)
