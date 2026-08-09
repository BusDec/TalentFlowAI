"""Tests for the deterministic tie-breaking engine."""

import pytest

from agents.tiebreaker import break_tie


# ── Deterministic ranking ───────────────────────────────────────────────────


def test_single_candidate_returned_unchanged():
    c = {"name": "Alice", "age": 30, "qual_pct": 80}
    result = break_tie([c])
    assert len(result) == 1
    assert result[0]["name"] == "Alice"


def test_empty_list():
    assert break_tie([]) == []


def test_default_rules_age_dominates():
    """Older candidate first when ages differ."""
    younger = {"name": "Bob",   "age": 25, "qual_pct": 90}
    older   = {"name": "Alice", "age": 35, "qual_pct": 60}
    result = break_tie([younger, older])
    assert [r["name"] for r in result] == ["Alice", "Bob"]


def test_default_rules_qual_pct_tiebreaker():
    """When ages are equal, higher qualification % wins."""
    a = {"name": "Alice", "age": 30, "qual_pct": 70}
    b = {"name": "Bob",   "age": 30, "qual_pct": 90}
    result = break_tie([a, b])
    assert [r["name"] for r in result] == ["Bob", "Alice"]


def test_default_rules_name_tiebreaker():
    """When age and qual_pct are both equal, alphabetical name wins."""
    a = {"name": "Charlie", "age": 30, "qual_pct": 80}
    b = {"name": "Alice",   "age": 30, "qual_pct": 80}
    c = {"name": "Bob",     "age": 30, "qual_pct": 80}
    result = break_tie([c, a, b])
    assert [r["name"] for r in result] == ["Alice", "Bob", "Charlie"]


def test_full_tie_break_cascade():
    """All three rules exercised in one call."""
    candidates = [
        {"name": "Zara",    "age": 30, "qual_pct": 85},
        {"name": "Alice",   "age": 30, "qual_pct": 85},
        {"name": "Bob",     "age": 35, "qual_pct": 60},
        {"name": "Charlie", "age": 35, "qual_pct": 90},
    ]
    result = break_tie(candidates)
    assert [r["name"] for r in result] == ["Charlie", "Bob", "Alice", "Zara"]


# ── Tie-break ordering (determinism) ───────────────────────────────────────


def test_same_input_same_output():
    """Calling break_tie twice with identical input yields identical order."""
    candidates = [
        {"name": "Dana",  "age": 28, "qual_pct": 75},
        {"name": "Eli",   "age": 28, "qual_pct": 75},
        {"name": "Fay",   "age": 32, "qual_pct": 60},
    ]
    r1 = break_tie(candidates)
    r2 = break_tie(candidates)
    assert [r["name"] for r in r1] == [r["name"] for r in r2]


def test_input_order_does_not_matter():
    """Reversing the input list does not change the sorted output."""
    fwd = [
        {"name": "Alice", "age": 30, "qual_pct": 80},
        {"name": "Bob",   "age": 30, "qual_pct": 80},
    ]
    rev = list(reversed(fwd))
    assert [r["name"] for r in break_tie(fwd)] == [r["name"] for r in break_tie(rev)]


def test_original_list_not_mutated():
    """break_tie must not modify the input list."""
    original = [
        {"name": "Bob",   "age": 25, "qual_pct": 90},
        {"name": "Alice", "age": 35, "qual_pct": 60},
    ]
    snapshot = [dict(c) for c in original]
    _ = break_tie(original)
    assert original == snapshot


# ── Custom rules ────────────────────────────────────────────────────────────


def test_custom_rule_order_name_first():
    """With name-only rule, alphabetical wins regardless of age."""
    candidates = [
        {"name": "Zack",  "age": 50, "qual_pct": 99},
        {"name": "Alice", "age": 20, "qual_pct": 10},
    ]
    result = break_tie(candidates, rules=["name"])
    assert [r["name"] for r in result] == ["Alice", "Zack"]


def test_custom_rule_qual_pct_only():
    candidates = [
        {"name": "Bob",   "age": 30, "qual_pct": 60},
        {"name": "Alice", "age": 30, "qual_pct": 95},
    ]
    result = break_tie(candidates, rules=["qual_pct"])
    assert [r["name"] for r in result] == ["Alice", "Bob"]


# ── Edge cases ──────────────────────────────────────────────────────────────


def test_missing_field_sorts_last():
    """Candidate missing the sort key sorts after those who have it."""
    with_val    = {"name": "Alice", "age": 30, "qual_pct": 80}
    without_val = {"name": "Bob",   "age": 30}  # qual_pct missing
    result = break_tie([without_val, with_val], rules=["qual_pct", "name"])
    assert [r["name"] for r in result] == ["Alice", "Bob"]


def test_extra_keys_preserved():
    """Candidate dicts with extra keys are not stripped."""
    c = {"name": "Alice", "age": 30, "qual_pct": 80, "dept": "Eng"}
    result = break_tie([c])
    assert result[0]["dept"] == "Eng"


def test_non_dict_candidate_raises():
    with pytest.raises(ValueError, match="Expected dict"):
        break_tie(["not-a-dict"])


def test_unknown_rule_raises():
    with pytest.raises(ValueError, match="Unknown tie-break rule"):
        break_tie([{"name": "A"}], rules=["bogus"])


def test_case_insensitive_name_sort():
    """Names differing only by case sort deterministically."""
    a = {"name": "alice", "age": 30, "qual_pct": 80}
    b = {"name": "Alice", "age": 30, "qual_pct": 80}
    # Both should appear — order is stable and deterministic.
    result = break_tie([a, b], rules=["name"])
    assert len(result) == 2
    # Both "alice" and "Alice" casefold to "alice", so relative order
    # is stable from input.  Just verify no crash and both present.
    names = {r["name"] for r in result}
    assert names == {"alice", "Alice"}
