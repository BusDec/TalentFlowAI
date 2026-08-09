"""Tests for LitigationCase — court case tracker + stay order banner."""

from datetime import date

from django.contrib.auth import get_user_model

from recruitment.models import AuditEvent, LitigationCase

User = get_user_model()


def _make_user(username="lit_user"):
    return User.objects.create_user(
        username=username,
        password="pass",
        email=f"{username}@neepco.local",
    )


# ── Model tests ─────────────────────────────────────────────────────────────


def test_litigation_case_create(tenant):
    """LitigationCase can be created with all required fields."""
    case = LitigationCase.objects.create(
        case_number="WP/1234/2026",
        court="Gauhati High Court",
        petitioner="Ram Kumar",
        filed_on=date(2026, 3, 15),
    )
    assert case.pk is not None
    assert case.case_number == "WP/1234/2026"
    assert case.court == "Gauhati High Court"
    assert case.petitioner == "Ram Kumar"
    assert case.status == "filed"  # default
    assert case.filed_on == date(2026, 3, 15)
    assert case.resolved_on is None
    assert case.created_at is not None


def test_litigation_case_str(tenant):
    """__str__ shows case_number and court."""
    case = LitigationCase.objects.create(
        case_number="WP/5678/2026",
        court="Delhi High Court",
        petitioner="Test Petitioner",
        filed_on=date(2026, 4, 1),
    )
    s = str(case)
    assert "WP/5678/2026" in s
    assert "Delhi High Court" in s


def test_litigation_case_application_fk(tenant, application):
    """LitigationCase can link to an application."""
    case = LitigationCase.objects.create(
        case_number="WP/9999/2026",
        court="Gauhati High Court",
        petitioner="Linked Petitioner",
        application=application,
        filed_on=date(2026, 5, 1),
    )
    assert case.application == application
    assert application.litigation_cases.count() == 1


def test_litigation_case_interim_orders_jsonfield(tenant):
    """interim_orders stores and retrieves structured JSON data."""
    orders = [
        {"type": "stay_order", "date": "2026-04-01", "text": "Stay granted on final selection."},
        {"type": "interim_direction", "date": "2026-05-15", "text": "Respondent to file counter."},
    ]
    case = LitigationCase.objects.create(
        case_number="WP/1111/2026",
        court="Gauhati High Court",
        petitioner="JSON Test",
        interim_orders=orders,
        filed_on=date(2026, 3, 1),
    )
    case.refresh_from_db()
    assert len(case.interim_orders) == 2
    assert case.interim_orders[0]["type"] == "stay_order"


def test_litigation_case_stay_active_property(tenant):
    """has_active_stay is True when a stay_order exists in interim_orders and case is active."""
    case = LitigationCase.objects.create(
        case_number="WP/2222/2026",
        court="Gauhati High Court",
        petitioner="Stay Test",
        status="filed",
        interim_orders=[{"type": "stay_order", "date": "2026-04-01", "text": "Stay granted."}],
        filed_on=date(2026, 3, 1),
    )
    assert case.has_active_stay is True

    # Resolved case — no longer active
    case.status = "resolved"
    case.resolved_on = date(2026, 6, 1)
    case.save()
    assert case.has_active_stay is False


def test_litigation_case_add_interim_order(tenant):
    """add_interim_order appends to the interim_orders JSONField."""
    case = LitigationCase.objects.create(
        case_number="WP/3333/2026",
        court="Gauhati High Court",
        petitioner="Add Order Test",
        filed_on=date(2026, 3, 1),
    )
    case.add_interim_order("stay_order", "Stay granted pending hearing.", date(2026, 4, 10))
    case.refresh_from_db()
    assert len(case.interim_orders) == 1
    assert case.interim_orders[0]["type"] == "stay_order"
    assert case.interim_orders[0]["text"] == "Stay granted pending hearing."


# ── View tests ──────────────────────────────────────────────────────────────


def test_application_detail_shows_stay_banner(tenant, application, staff_user):
    """Active stay on linked case renders an amber warning banner on application detail."""
    case = LitigationCase.objects.create(
        case_number="WP/4444/2026",
        court="Gauhati High Court",
        petitioner="Banner Test",
        application=application,
        status="filed",
        interim_orders=[{"type": "stay_order", "date": "2026-04-01", "text": "Stay granted."}],
        filed_on=date(2026, 3, 1),
    )

    from django.test import Client

    client = Client(HTTP_HOST="neepco.localhost")
    client.force_login(staff_user)
    response = client.get(f"/applications/{application.application_id}/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "stay" in content.lower()
    assert "WP/4444/2026" in content


def test_application_detail_no_stay_banner_when_no_stay(tenant, application, staff_user):
    """No amber banner when case has no stay_order in interim_orders."""
    LitigationCase.objects.create(
        case_number="WP/5555/2026",
        court="Gauhati High Court",
        petitioner="No Stay Test",
        application=application,
        status="filed",
        interim_orders=[{"type": "notice", "date": "2026-04-01", "text": "Notice issued."}],
        filed_on=date(2026, 3, 1),
    )

    from django.test import Client

    client = Client(HTTP_HOST="neepco.localhost")
    client.force_login(staff_user)
    response = client.get(f"/applications/{application.application_id}/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "WP/5555/2026" not in content


def test_litigation_list_view(tenant, staff_user):
    """HR manager can view the litigation case list."""
    LitigationCase.objects.create(
        case_number="WP/6666/2026",
        court="Gauhati High Court",
        petitioner="List Test",
        filed_on=date(2026, 3, 1),
    )

    from django.test import Client

    client = Client(HTTP_HOST="neepco.localhost")
    client.force_login(staff_user)
    response = client.get("/litigation/")
    assert response.status_code == 200
    assert "WP/6666/2026" in response.content.decode()


def test_litigation_add_order_view(tenant, staff_user):
    """HR manager can add an interim order via POST."""
    case = LitigationCase.objects.create(
        case_number="WP/7777/2026",
        court="Gauhati High Court",
        petitioner="Add Order View Test",
        filed_on=date(2026, 3, 1),
    )

    from django.test import Client

    client = Client(HTTP_HOST="neepco.localhost")
    client.force_login(staff_user)
    response = client.post(
        f"/litigation/{case.pk}/add-order/",
        data={"order_type": "stay_order", "order_text": "Stay granted by court."},
    )
    assert response.status_code == 302
    case.refresh_from_db()
    assert len(case.interim_orders) == 1
    assert case.interim_orders[0]["type"] == "stay_order"


# ── Audit tests ─────────────────────────────────────────────────────────────


def test_litigation_case_audit_on_status_change(tenant, application, staff_user):
    """Status change on LitigationCase creates an AuditEvent."""
    case = LitigationCase.objects.create(
        case_number="WP/8888/2026",
        court="Gauhati High Court",
        petitioner="Audit Test",
        application=application,
        status="filed",
        filed_on=date(2026, 3, 1),
    )

    from django.test import Client

    client = Client(HTTP_HOST="neepco.localhost")
    client.force_login(staff_user)
    client.post(
        f"/litigation/{case.pk}/update-status/",
        data={"status": "resolved", "resolved_on": "2026-06-01", "final_order_text": "Writ dismissed."},
    )
    case.refresh_from_db()
    assert case.status == "resolved"

    event = AuditEvent.objects.filter(
        application=application,
        field_name="litigation_status",
    ).first()
    assert event is not None
    assert event.old_value == "filed"
    assert event.new_value == "resolved"
