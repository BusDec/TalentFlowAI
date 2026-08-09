"""Tests for Interview models — InterviewPanel, InterviewSlot, InterviewScore."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from recruitment.models import (
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
