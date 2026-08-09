"""Tests for recruitment.archival — eligibility detection + hash-chain.

Phase 4.10
"""

from datetime import date, timedelta

import pytest

from recruitment.archival import (
    TERMINAL_STATUSES,
    archive_eligible,
    hash_row,
    verify_chain,
)
from recruitment.models import Application, AuditEvent, Candidate, Post
from recruitment.audit import log_audit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def old_advertisement(db, tenant):
    """Advertisement whose closing_date is >1 year ago."""
    from recruitment.models import Advertisement

    advt = Advertisement.objects.create(
        advt_number="TF-OLD-2024",
        title="Old Advt",
        published_date="2024-01-01",
        closing_date=date.today() - timedelta(days=400),
    )
    post = Post.objects.create(
        advertisement=advt,
        name="Engineer",
        post_code="ENG-OLD",
        vacancies=1,
        qualification="B.Tech",
    )
    return advt, post


@pytest.fixture
def recent_advertisement(db, tenant):
    """Advertisement whose closing_date is within the last year."""
    from recruitment.models import Advertisement

    advt = Advertisement.objects.create(
        advt_number="TF-NEW-2026",
        title="Recent Advt",
        published_date="2026-06-01",
        closing_date=date.today() - timedelta(days=30),
    )
    post = Post.objects.create(
        advertisement=advt,
        name="Manager",
        post_code="MGR-NEW",
        vacancies=1,
        qualification="MBA",
    )
    return advt, post


_counter = 0


def _make_application(post, status, suffix=""):
    global _counter
    _counter += 1
    n = str(_counter)
    candidate = Candidate.objects.create(
        first_name=f"C{suffix[:10]}",
        last_name="Test",
        email=f"cand{n}@example.com",
        mobile=f"98765{n:>05}",
    )
    return Application.objects.create(
        post=post,
        candidate=candidate,
        application_id=f"TF-ARC-{n}",
        status=status,
    )


# ---------------------------------------------------------------------------
# Eligibility detection
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_eligible_old_closing_terminal_status(old_advertisement, tenant):
    """Terminal-status apps with closing_date >1yr ago are eligible."""
    _, post = old_advertisement
    for status in TERMINAL_STATUSES:
        _make_application(post, status, suffix=status)

    eligible = archive_eligible()
    assert eligible.count() == len(TERMINAL_STATUSES)
    assert set(eligible.values_list("status", flat=True)) == set(TERMINAL_STATUSES)


@pytest.mark.django_db
def test_not_eligible_recent_closing(recent_advertisement, tenant):
    """Terminal-status apps with closing_date <1yr ago are NOT eligible."""
    _, post = recent_advertisement
    for status in TERMINAL_STATUSES:
        _make_application(post, status, suffix=f"recent-{status}")

    assert archive_eligible().count() == 0


@pytest.mark.django_db
def test_not_eligible_nonterminal_status(old_advertisement, tenant):
    """Non-terminal apps with old closing_date are NOT eligible."""
    _, post = old_advertisement
    for status in ("received", "shortlisted", "interview", "offered"):
        _make_application(post, status, suffix=f"nt-{status}")

    assert archive_eligible().count() == 0


@pytest.mark.django_db
def test_eligible_ignores_nonterminal_among_old(old_advertisement, tenant):
    """Only terminal apps among old ads are returned; non-terminal filtered out."""
    _, post = old_advertisement
    _make_application(post, "joined", suffix="j")
    _make_application(post, "received", suffix="r")
    _make_application(post, "rejected", suffix="rej")

    eligible = archive_eligible()
    assert eligible.count() == 2
    assert set(eligible.values_list("status", flat=True)) == {"joined", "rejected"}


@pytest.mark.django_db
def test_empty_queryset_when_no_applications(tenant):
    """No applications at all → empty queryset."""
    assert archive_eligible().count() == 0


# ---------------------------------------------------------------------------
# Hash-chain
# ---------------------------------------------------------------------------

def _make_event(pk=1, ts_iso="2026-08-09T12:00:00+00:00", field="status", old="received", new="joined"):
    """Build a minimal mock that quacks like an AuditEvent for hashing."""
    class _FakeEvent:
        pass

    e = _FakeEvent()
    e.pk = pk
    e.timestamp = type("T", (), {"isoformat": staticmethod(lambda: ts_iso)})()
    e.actor_id = 10
    e.application_id = 100
    e.field_name = field
    e.old_value = old
    e.new_value = new
    e.reason = ""
    e.tenant_schema = "neepco"
    return e


def test_hash_row_deterministic():
    """Same inputs always produce the same hash."""
    ev = _make_event()
    h1 = hash_row(ev, "abc")
    h2 = hash_row(ev, "abc")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_hash_row_changes_with_prev_hash():
    """Different prev_hash produces a different result."""
    ev = _make_event()
    assert hash_row(ev, "aaa") != hash_row(ev, "bbb")


def test_hash_row_changes_with_event_data():
    """Different event data produces a different result."""
    ev1 = _make_event(pk=1)
    ev2 = _make_event(pk=2)
    assert hash_row(ev1, "") != hash_row(ev2, "")


def test_verify_chain_valid():
    """A correctly computed chain passes verification."""
    events = [_make_event(pk=i) for i in range(1, 4)]
    hashes = []
    prev = ""
    for ev in events:
        h = hash_row(ev, prev)
        hashes.append(h)
        prev = h

    assert verify_chain(events, hashes) is True


def test_verify_chain_tampered():
    """Flipping one hash causes verification failure."""
    events = [_make_event(pk=i) for i in range(1, 4)]
    hashes = []
    prev = ""
    for ev in events:
        h = hash_row(ev, prev)
        hashes.append(h)
        prev = h

    # Tamper with middle hash
    hashes[1] = "0" * 64
    assert verify_chain(events, hashes) is False


def test_verify_chain_length_mismatch():
    """Mismatched list lengths fail verification."""
    events = [_make_event(pk=1)]
    hashes = [hash_row(events[0], ""), "extra"]
    assert verify_chain(events, hashes) is False


def test_verify_chain_empty():
    """Empty chain is trivially valid."""
    assert verify_chain([], []) is True


def test_verify_chain_single_element():
    """Single-event chain works correctly."""
    ev = _make_event(pk=1)
    h = hash_row(ev, "")
    assert verify_chain([ev], [h]) is True
    assert verify_chain([ev], ["bad"]) is False


@pytest.mark.django_db
def test_hash_chain_with_real_audit_events(application, staff_user, tenant):
    """Hash-chain over real AuditEvent rows from the ORM."""
    # Create two audit events via the normal save path
    application.status = "shortlisted"
    application.save(audit_actor=staff_user)
    application.status = "joined"
    application.save(audit_actor=staff_user)

    events = list(AuditEvent.objects.filter(application=application).order_by("timestamp"))
    assert len(events) == 2

    # Build chain
    hashes = []
    prev = ""
    for ev in events:
        h = hash_row(ev, prev)
        hashes.append(h)
        prev = h

    assert verify_chain(events, hashes) is True

    # Tamper: swap hashes
    hashes[0], hashes[1] = hashes[1], hashes[0]
    assert verify_chain(events, hashes) is False
