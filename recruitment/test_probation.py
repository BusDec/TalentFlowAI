"""Tests for ProbationRecord — probation tracking and confirmation."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from conftest import TENANT_DOMAIN, create_tenant, make_staff_user
from recruitment.models import ProbationRecord

User = get_user_model()


# ── Model tests ─────────────────────────────────────────────────────────────


def test_probation_record_create(tenant, application):
    """ProbationRecord can be created with all required fields."""
    record = ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
    )
    assert record.pk is not None
    assert record.created_at is not None
    assert record.updated_at is not None


def test_probation_record_str_on_probation(tenant, application):
    """__str__ shows application ID and 'On Probation' when not confirmed."""
    record = ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
    )
    s = str(record)
    assert "TF20260001" in s
    assert "On Probation" in s


def test_probation_record_str_confirmed(tenant, application):
    """__str__ shows 'Confirmed' when confirmed_on is set."""
    record = ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
        confirmed_on=date(2027, 1, 15),
    )
    s = str(record)
    assert "Confirmed" in s


def test_probation_record_is_confirmed_property(tenant, application):
    """is_confirmed is True when confirmed_on is set, False otherwise."""
    record = ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
    )
    assert record.is_confirmed is False
    record.confirmed_on = date(2027, 1, 15)
    assert record.is_confirmed is True


def test_probation_record_is_expired_property(tenant, application):
    """is_expired is True when end_date has passed and not confirmed."""
    record = ProbationRecord.objects.create(
        application=application,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 6, 30),
    )
    assert record.is_expired is True


def test_probation_record_not_expired_when_confirmed(tenant, application):
    """is_expired is False even if end_date passed, when confirmed."""
    record = ProbationRecord.objects.create(
        application=application,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 6, 30),
        confirmed_on=date(2025, 6, 15),
    )
    assert record.is_expired is False


def test_probation_record_bond_amount(tenant, application):
    """bond_amount stores a Decimal value."""
    record = ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
        bond_amount=Decimal("50000.00"),
    )
    record.refresh_from_db()
    assert record.bond_amount == Decimal("50000.00")


def test_probation_record_notes(tenant, application):
    """notes field stores free text."""
    record = ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
        notes="Must serve 6 months or pay bond.",
    )
    record.refresh_from_db()
    assert "Must serve" in record.notes


def test_probation_record_one_to_one_application(tenant, application):
    """One ProbationRecord per application (OneToOneField)."""
    ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
    )
    assert hasattr(application, "probation_record")
    assert application.probation_record is not None


# ── View tests ──────────────────────────────────────────────────────────────


def test_probation_list_view_hr_manager(tenant, application, staff_user):
    """HR manager can view the probation list page."""
    ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
    )
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.get(reverse("probation_list"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "TF20260001" in content
    assert "On Probation" in content


def test_probation_list_view_recruiter(tenant, application, recruiter_user):
    """Recruiter can also view the probation list."""
    ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
    )
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(recruiter_user)
    response = client.get(reverse("probation_list"))
    assert response.status_code == 200


def test_probation_list_view_viewer_denied(tenant, application, viewer_user):
    """Viewer role cannot access probation list (needs recruiter or hr_manager)."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(viewer_user)
    response = client.get(reverse("probation_list"))
    assert response.status_code == 403


def test_probation_confirm_view(tenant, application, staff_user):
    """HR manager can confirm an employee via POST."""
    record = ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
    )
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.post(reverse("probation_confirm", args=[record.pk]))
    assert response.status_code == 302
    record.refresh_from_db()
    assert record.is_confirmed is True
    assert record.confirmed_on == date.today()


def test_probation_confirm_already_confirmed(tenant, application, staff_user):
    """Confirming an already confirmed employee redirects with info message."""
    record = ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
        confirmed_on=date(2027, 1, 15),
    )
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.post(reverse("probation_confirm", args=[record.pk]))
    assert response.status_code == 302
    record.refresh_from_db()
    assert record.confirmed_on == date(2027, 1, 15)  # unchanged


def test_probation_confirm_get_not_allowed(tenant, application, staff_user):
    """GET request to confirm endpoint returns 405."""
    record = ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
    )
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.get(reverse("probation_confirm", args=[record.pk]))
    assert response.status_code == 405


def test_probation_list_displays_bond_amount(tenant, application, staff_user):
    """Bond amount displays on the list page when set."""
    ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
        bond_amount=Decimal("75000.00"),
    )
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.get(reverse("probation_list"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "75000" in content


def test_probation_list_empty(tenant, staff_user):
    """Empty state renders when no records exist."""
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.get(reverse("probation_list"))
    assert response.status_code == 200
    assert "No probation records found" in response.content.decode()


def test_probation_list_shows_expired_status(tenant, application, staff_user):
    """Expired probation shows 'Expired' badge."""
    ProbationRecord.objects.create(
        application=application,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 6, 30),
    )
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.get(reverse("probation_list"))
    assert response.status_code == 200
    assert "Expired" in response.content.decode()


def test_probation_list_shows_confirmed_status(tenant, application, staff_user):
    """Confirmed probation shows 'Confirmed' badge."""
    ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
        confirmed_on=date(2027, 1, 15),
    )
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.get(reverse("probation_list"))
    assert response.status_code == 200
    assert "Confirmed" in response.content.decode()


def test_probation_confirm_button_hidden_when_confirmed(tenant, application, staff_user):
    """Confirm button is not shown for already confirmed records."""
    ProbationRecord.objects.create(
        application=application,
        start_date=date(2026, 8, 1),
        end_date=date(2027, 1, 31),
        confirmed_on=date(2027, 1, 15),
    )
    client = Client(HTTP_HOST=TENANT_DOMAIN)
    client.force_login(staff_user)
    response = client.get(reverse("probation_list"))
    content = response.content.decode()
    assert "Confirm" not in content or "Confirmed" in content
