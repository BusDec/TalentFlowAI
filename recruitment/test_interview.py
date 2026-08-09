"""Tests for Interview models, views, auto-schedule signal, and score aggregation."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from conftest import TENANT_DOMAIN, make_staff_user
from recruitment.models import (
    Application,
    Candidate,
    InterviewPanel,
    InterviewScore,
    InterviewSlot,
    Post,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def post(advertisement):
    return advertisement.posts.first()


@pytest.fixture
def panel(db, post, staff_user):
    """An InterviewPanel with one M2M member."""
    p = InterviewPanel.objects.create(
        post=post,
        name="Panel A",
        sitting_fee=Decimal("2000.00"),
    )
    p.members.add(staff_user)
    return p


@pytest.fixture
def slot(db, panel, application):
    """A pending InterviewSlot."""
    return InterviewSlot.objects.create(
        panel=panel,
        application=application,
        datetime=timezone.now() + timedelta(days=7),
        duration_minutes=60,
    )


@pytest.fixture
def score(db, slot, staff_user):
    """An InterviewScore linked to the slot."""
    return InterviewScore.objects.create(
        slot=slot,
        panel_member=staff_user,
        score=Decimal("7.5"),
        comments="Good technical depth",
    )


# ── InterviewPanel tests ─────────────────────────────────────────────────────


class TestInterviewPanel:
    def test_create_panel(self, db, post, staff_user):
        """Panel can be created with post FK, name, sitting_fee, and M2M members."""
        panel = InterviewPanel.objects.create(
            post=post,
            name="Panel B",
            sitting_fee=Decimal("1500.00"),
            external_members=[{"name": "Dr. Rao", "org": "IIT"}],
        )
        panel.members.add(staff_user)
        assert panel.pk is not None
        assert panel.post == post
        assert panel.name == "Panel B"
        assert panel.sitting_fee == Decimal("1500.00")
        assert panel.members.count() == 1
        assert panel.external_members == [{"name": "Dr. Rao", "org": "IIT"}]
        assert panel.created_at is not None

    def test_panel_str(self, panel):
        s = str(panel)
        assert "Panel A" in s

    def test_panel_sitting_fee_nullable(self, db, post):
        """sitting_fee can be null."""
        panel = InterviewPanel.objects.create(
            post=post,
            name="Free Panel",
            sitting_fee=None,
        )
        assert panel.sitting_fee is None

    def test_panel_external_members_default_empty(self, db, post):
        """external_members defaults to empty list."""
        panel = InterviewPanel.objects.create(
            post=post,
            name="Internal Only",
        )
        assert panel.external_members == []


# ── InterviewSlot tests ──────────────────────────────────────────────────────


class TestInterviewSlot:
    def test_create_slot(self, slot, panel, application):
        """Slot can be created with panel FK, application FK, datetime, duration."""
        assert slot.pk is not None
        assert slot.panel == panel
        assert slot.application == application
        assert slot.duration_minutes == 60
        assert slot.status == "scheduled"

    def test_slot_str(self, slot):
        s = str(slot)
        assert "Panel A" in s or "slot" in s.lower() or "Slot" in s

    def test_slot_default_duration(self, db, panel, application):
        """duration_minutes defaults to 30."""
        s = InterviewSlot.objects.create(
            panel=panel,
            application=application,
            datetime=timezone.now(),
        )
        assert s.duration_minutes == 30

    def test_slot_status_transitions(self, slot):
        """Slot status can transition through the workflow."""
        assert slot.status == "scheduled"
        slot.status = "in_progress"
        slot.save()
        slot.refresh_from_db()
        assert slot.status == "in_progress"
        slot.status = "completed"
        slot.save()
        slot.refresh_from_db()
        assert slot.status == "completed"

    def test_slot_status_cancelled(self, slot):
        """Slot can be cancelled."""
        slot.status = "cancelled"
        slot.save()
        slot.refresh_from_db()
        assert slot.status == "cancelled"

    def test_slot_notes(self, slot):
        """Notes can be set on a slot."""
        slot.notes = "Candidate requested afternoon slot"
        slot.save()
        slot.refresh_from_db()
        assert slot.notes == "Candidate requested afternoon slot"


# ── InterviewScore tests ─────────────────────────────────────────────────────


class TestInterviewScore:
    def test_create_score(self, score, slot, staff_user):
        """Score can be created with slot FK, panel_member FK, score, comments."""
        assert score.pk is not None
        assert score.slot == slot
        assert score.panel_member == staff_user
        assert score.score == Decimal("7.5")
        assert score.comments == "Good technical depth"
        assert score.created_at is not None

    def test_score_str(self, score):
        s = str(score)
        assert "7.5" in s

    def test_score_panel_member_nullable(self, db, slot):
        """panel_member can be null (anonymous external scorer)."""
        sc = InterviewScore.objects.create(
            slot=slot,
            score=Decimal("6.0"),
            comments="Average",
        )
        assert sc.panel_member is None

    def test_multiple_scores_per_slot(self, db, slot, staff_user):
        """A slot can have multiple scores from different panel members."""
        s1 = InterviewScore.objects.create(
            slot=slot, panel_member=staff_user, score=Decimal("8.0"),
        )
        s2 = InterviewScore.objects.create(
            slot=slot, score=Decimal("6.5"), comments="External",
        )
        assert slot.scores.count() == 2


# ── Round-trip integration test ──────────────────────────────────────────────


def test_panel_slot_score_round_trip(db, post, application, staff_user):
    """Full round-trip: panel → slot → score, all queryable and linked."""
    panel = InterviewPanel.objects.create(
        post=post, name="RT Panel", sitting_fee=Decimal("3000.00"),
    )
    panel.members.add(staff_user)

    slot = InterviewSlot.objects.create(
        panel=panel,
        application=application,
        datetime=timezone.now() + timedelta(days=3),
        duration_minutes=45,
        status="scheduled",
    )

    score = InterviewScore.objects.create(
        slot=slot,
        panel_member=staff_user,
        score=Decimal("9.0"),
        comments="Excellent",
    )

    # Verify forward and reverse relations
    assert panel.slots.count() == 1
    assert panel.slots.first() == slot
    assert slot.scores.count() == 1
    assert slot.scores.first() == score
    assert score.slot.panel == panel
    assert score.panel_member == staff_user

    # Verify post linkage
    assert panel.post == post
    assert post.interview_panels.count() == 1


# ═══════════════════════════════════════════════════════════════════════════════
# View-level tests — Phase 3 Task 2: Interview views + auto-schedule
# ═══════════════════════════════════════════════════════════════════════════════


def _client(user):
    """Return a test client logged in as *user* on the tenant domain."""
    c = Client(HTTP_HOST=TENANT_DOMAIN)
    c.force_login(user)
    return c


# ── constitute panel (hr_manager) ────────────────────────────────────────────


class TestInterviewPanelCreateView:
    """HR manager can constitute an interview panel for a post."""

    def test_panel_create_get_renders_form(self, tenant, staff_user, advertisement):
        """GET renders the panel creation form."""
        post = advertisement.posts.first()
        c = _client(staff_user)
        resp = c.get(reverse("interview_panel_create", args=[post.pk]))
        assert resp.status_code == 200
        assert b"Panel" in resp.content

    def test_panel_create_post_hr_manager(self, tenant, staff_user, advertisement):
        """HR manager can POST to create a panel; redirects to interview results."""
        post = advertisement.posts.first()
        c = _client(staff_user)
        resp = c.post(reverse("interview_panel_create", args=[post.pk]), {
            "name": "Panel Alpha",
            "sitting_fee": "2500.00",
            "member_ids": str(staff_user.pk),
        })
        assert resp.status_code == 302
        panel = InterviewPanel.objects.get(post=post, name="Panel Alpha")
        assert panel.sitting_fee == Decimal("2500.00")
        assert panel.members.count() == 1

    def test_panel_create_requires_hr_manager_role(self, tenant, viewer_user, advertisement):
        """Viewer role is denied panel creation."""
        post = advertisement.posts.first()
        c = _client(viewer_user)
        resp = c.get(reverse("interview_panel_create", args=[post.pk]))
        assert resp.status_code == 403


# ── schedule slot (recruiter) ────────────────────────────────────────────────


class TestInterviewScheduleView:
    """Recruiter can schedule an interview slot for a candidate."""

    def test_schedule_slot_post_recruiter(self, tenant, recruiter_user, panel, application):
        """Recruiter can POST to schedule a slot; redirects to interview results."""
        c = _client(recruiter_user)
        dt = (timezone.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
        resp = c.post(reverse("interview_schedule", args=[panel.pk]), {
            "application_id": application.application_id,
            "datetime": dt,
            "duration_minutes": "45",
            "notes": "Morning session",
        })
        assert resp.status_code == 302
        slot = InterviewSlot.objects.get(panel=panel, application=application)
        assert slot.duration_minutes == 45
        assert slot.notes == "Morning session"
        assert slot.status == "scheduled"

    def test_schedule_slot_requires_recruiter_role(self, tenant, viewer_user, panel, application):
        """Viewer role is denied slot scheduling."""
        c = _client(viewer_user)
        dt = (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        resp = c.post(reverse("interview_schedule", args=[panel.pk]), {
            "application_id": application.application_id,
            "datetime": dt,
            "duration_minutes": "30",
        })
        assert resp.status_code == 403

    def test_schedule_slot_invalid_application(self, tenant, recruiter_user, panel):
        """Scheduling with nonexistent application_id shows error."""
        c = _client(recruiter_user)
        dt = (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        resp = c.post(reverse("interview_schedule", args=[panel.pk]), {
            "application_id": "NONEXISTENT999",
            "datetime": dt,
            "duration_minutes": "30",
        })
        # Should re-render the form with error (200) or redirect with error message
        assert resp.status_code in (200, 302)
        assert InterviewSlot.objects.count() == 0


# ── enter score ──────────────────────────────────────────────────────────────


class TestInterviewScoreView:
    """Panel members can enter scores for a scheduled slot."""

    def test_enter_score_post(self, tenant, staff_user, slot):
        """Authenticated user can POST a score for a slot."""
        c = _client(staff_user)
        resp = c.post(reverse("interview_score", args=[slot.pk]), {
            "score": "8.5",
            "comments": "Strong candidate with good domain knowledge.",
        })
        assert resp.status_code == 302
        sc = InterviewScore.objects.get(slot=slot, panel_member=staff_user)
        assert sc.score == Decimal("8.5")
        assert sc.comments == "Strong candidate with good domain knowledge."

    def test_enter_multiple_scores(self, tenant, staff_user, recruiter_user, slot):
        """Multiple users can score the same slot."""
        c1 = _client(staff_user)
        c1.post(reverse("interview_score", args=[slot.pk]), {
            "score": "7.0", "comments": "Good",
        })
        c2 = _client(recruiter_user)
        c2.post(reverse("interview_score", args=[slot.pk]), {
            "score": "8.0", "comments": "Excellent",
        })
        assert slot.scores.count() == 2

    def test_score_requires_authenticated(self, tenant, slot):
        """Unauthenticated user cannot score."""
        c = Client(HTTP_HOST=TENANT_DOMAIN)
        resp = c.post(reverse("interview_score", args=[slot.pk]), {
            "score": "5.0", "comments": "",
        })
        assert resp.status_code == 302  # redirect to login


# ── view aggregate results ───────────────────────────────────────────────────


class TestInterviewResultsView:
    """Aggregate score results for a post's interview panels."""

    def test_results_view_renders(self, tenant, staff_user, advertisement, panel, slot, score):
        """GET renders aggregate results including average score."""
        post = advertisement.posts.first()
        c = _client(staff_user)
        resp = c.get(reverse("interview_results", args=[post.pk]))
        assert resp.status_code == 200
        assert b"Panel A" in resp.content

    def test_results_shows_aggregate_scores(self, tenant, staff_user, advertisement, panel, slot):
        """Results page shows per-candidate average when scores exist."""
        # Add two scores for the slot
        InterviewScore.objects.create(
            slot=slot, panel_member=staff_user, score=Decimal("7.0"),
        )
        InterviewScore.objects.create(
            slot=slot, score=Decimal("9.0"), comments="External scorer",
        )
        post = advertisement.posts.first()
        c = _client(staff_user)
        resp = c.get(reverse("interview_results", args=[post.pk]))
        assert resp.status_code == 200
        # The average should be 8.0
        assert b"8.0" in resp.content

    def test_results_empty_panels(self, tenant, staff_user, advertisement):
        """Results page renders even when no panels exist."""
        post = advertisement.posts.first()
        c = _client(staff_user)
        resp = c.get(reverse("interview_results", args=[post.pk]))
        assert resp.status_code == 200


# ── auto-schedule signal on Application → interview ──────────────────────────


class TestAutoScheduleSignal:
    """When an Application's status changes to 'interview', a slot is auto-created."""

    def test_auto_schedule_on_status_change_to_interview(self, tenant, application, panel):
        """Transitioning application to 'interview' auto-creates an InterviewSlot."""
        # Ensure application.post matches panel.post
        assert application.post == panel.post

        application.status = "interview"
        application.save()

        slot = InterviewSlot.objects.filter(
            panel=panel,
            application=application,
        ).first()
        assert slot is not None
        assert slot.status == "scheduled"
        assert slot.duration_minutes == 30

    def test_no_auto_schedule_without_panel(self, tenant, application):
        """No auto-schedule when no panel exists for the post."""
        application.status = "interview"
        application.save()
        assert InterviewSlot.objects.filter(application=application).count() == 0

    def test_no_duplicate_slot_on_resave(self, tenant, application, panel):
        """Saving an already-interview application doesn't duplicate the slot."""
        application.status = "interview"
        application.save()
        assert InterviewSlot.objects.filter(application=application).count() == 1

        # Re-save without changing status
        application.save()
        assert InterviewSlot.objects.filter(application=application).count() == 1

    def test_no_auto_schedule_for_other_statuses(self, tenant, application, panel):
        """Changing to non-interview status doesn't create a slot."""
        application.status = "shortlisted"
        application.save()
        assert InterviewSlot.objects.filter(application=application).count() == 0
