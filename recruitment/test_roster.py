def test_roster_generator_100_points():
    from recruitment.roster import build_roster

    entries = build_roster(None, 2026)  # post unused by pure generator for now
    assert len(entries) == 100
    cats = {e["category"] for e in entries}
    assert cats == {"UR", "SC", "ST", "OBC", "EWS"}


def test_roster_model(tenant, advertisement):
    from recruitment.models import PostBasedRoster

    post = advertisement.posts.first()
    r = PostBasedRoster.objects.create(
        post=post,
        cycle_start_year=2026,
        roster_points=[{"serial": 1, "category": "UR", "point_type": "l"}],
    )
    assert r.current_position == 1


def test_roster_pattern_dopt():
    # Standard DoPT 100-point opening: 1 UR, 2 SC, 3 UR, 4 UR, 5 ST, 6 UR, 7 UR, 8 UR, 9 OBC, 10 UR ...
    from recruitment.roster import build_roster

    entries = build_roster(None, 2026)
    assert entries[0] == {"serial": 1, "category": "UR", "point_type": "l"}
    assert entries[1] == {"serial": 2, "category": "SC", "point_type": "r"}
    assert entries[8] == {"serial": 9, "category": "OBC", "point_type": "r"}


def test_roster_advances_on_joined(tenant, advertisement, application):
    """When an Application transitions to 'joined', the post's roster
    current_position should advance by 1."""
    from recruitment.models import PostBasedRoster
    from recruitment.roster import build_roster

    post = advertisement.posts.first()
    PostBasedRoster.objects.create(
        post=post,
        cycle_start_year=2026,
        roster_points=build_roster(post, 2026),
    )
    assert post.roster.current_position == 1

    application.status = "joined"
    application.save()
    post.roster.refresh_from_db()
    assert post.roster.current_position == 2


def test_roster_does_not_advance_on_non_joined(tenant, advertisement, application):
    """Saving an application with a status other than 'joined' should not
    advance the roster position."""
    from recruitment.models import PostBasedRoster
    from recruitment.roster import build_roster

    post = advertisement.posts.first()
    PostBasedRoster.objects.create(
        post=post,
        cycle_start_year=2026,
        roster_points=build_roster(post, 2026),
    )
    assert post.roster.current_position == 1

    application.status = "shortlisted"
    application.save()
    post.roster.refresh_from_db()
    assert post.roster.current_position == 1


def test_roster_advances_idempotent(tenant, advertisement, application):
    """Saving an already-'joined' application again should NOT double-advance
    the roster."""
    from recruitment.models import PostBasedRoster
    from recruitment.roster import build_roster

    post = advertisement.posts.first()
    PostBasedRoster.objects.create(
        post=post,
        cycle_start_year=2026,
        roster_points=build_roster(post, 2026),
    )

    application.status = "joined"
    application.save()
    post.roster.refresh_from_db()
    assert post.roster.current_position == 2

    # Save again while still 'joined' -- should not advance again.
    application.save()
    post.roster.refresh_from_db()
    assert post.roster.current_position == 2


def test_dopt_generate_action(api_client, staff_user, advertisement):
    """POST action=dopt_generate creates a PostBasedRoster and redirects."""
    from django.urls import reverse

    from recruitment.models import PostBasedRoster

    post = advertisement.posts.first()
    api_client.force_login(staff_user)  # hr_manager
    response = api_client.post(
        reverse("roster_view", args=[post.id]),
        {"action": "dopt_generate"},
    )
    assert response.status_code == 302
    assert PostBasedRoster.objects.filter(post=post).exists()
    dopt = PostBasedRoster.objects.get(post=post)
    assert len(dopt.roster_points) == 100
    assert dopt.current_position == 1
    assert dopt.cycle_start_year == 2026


def test_dopt_grid_rendered(api_client, staff_user, advertisement):
    """GET roster_view with existing PostBasedRoster renders the DoPT grid."""
    from django.urls import reverse

    from recruitment.models import PostBasedRoster
    from recruitment.roster import build_roster

    post = advertisement.posts.first()
    PostBasedRoster.objects.create(
        post=post,
        cycle_start_year=2026,
        roster_points=build_roster(post, 2026),
    )
    api_client.force_login(staff_user)
    response = api_client.get(reverse("roster_view", args=[post.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "DoPT 100-Point Roster" in content
    # Check serial 1 and category SC appear in the grid
    assert "1" in content
    assert "SC" in content
    # current_position=1 cell should be highlighted
    assert "roster-current" in content
