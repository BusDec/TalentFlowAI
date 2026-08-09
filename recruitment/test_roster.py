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
