from django.db import connection


def log_audit(actor, application, field_name, old_value, new_value, reason=""):
    from .models import AuditEvent

    return AuditEvent.objects.create(
        actor=actor,
        tenant_schema=connection.schema_name,
        application=application,
        field_name=field_name,
        old_value="" if old_value is None else str(old_value),
        new_value="" if new_value is None else str(new_value),
        reason=reason,
    )
