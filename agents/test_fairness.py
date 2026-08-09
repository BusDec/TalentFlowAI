"""Tests for the fairness analysis engine."""

from agents.fairness import (
    compute_adverse_impact,
    compute_statistical_parity,
    sanitize_resume_for_prompt,
)


# ── Adverse Impact (4/5ths rule) ────────────────────────────────────────────


def test_adverse_impact_flags_sc_below_threshold():
    """SC 40 % vs UR 60 % → SC is below the 80 % threshold → flagged."""
    rates = {"sc": 0.40, "ur": 0.60, "obc": 0.55, "st": 0.50}
    result = compute_adverse_impact(rates)

    assert result["has_adverse_impact"] is True
    assert "sc" in result["flagged"]
    assert result["threshold"] == 0.60 * 0.8  # 0.48


def test_adverse_impact_no_flag_when_all_above_threshold():
    rates = {"sc": 0.50, "ur": 0.60, "obc": 0.55}
    result = compute_adverse_impact(rates)

    assert result["has_adverse_impact"] is False
    assert result["flagged"] == []


def test_adverse_impact_empty_input():
    result = compute_adverse_impact({})
    assert result["has_adverse_impact"] is False
    assert result["categories"] == []


def test_adverse_impact_single_category():
    result = compute_adverse_impact({"ur": 0.50})
    assert result["has_adverse_impact"] is False
    assert result["max_rate"] == 0.50
    assert result["threshold"] == 0.40


def test_adverse_impact_ratio_to_max():
    rates = {"sc": 0.40, "ur": 0.60}
    result = compute_adverse_impact(rates)

    sc_detail = next(c for c in result["categories"] if c["category"] == "sc")
    ur_detail = next(c for c in result["categories"] if c["category"] == "ur")

    assert abs(sc_detail["ratio_to_max"] - 0.40 / 0.60) < 1e-9
    assert ur_detail["ratio_to_max"] == 1.0


# ── Statistical Parity ──────────────────────────────────────────────────────


def test_statistical_parity_overall_rate():
    rates = {"sc": 0.40, "ur": 0.60, "obc": 0.50}
    result = compute_statistical_parity(rates)

    expected_overall = (0.40 + 0.60 + 0.50) / 3
    assert abs(result["overall_rate"] - expected_overall) < 1e-9


def test_statistical_parity_deviations():
    rates = {"sc": 0.40, "ur": 0.60, "obc": 0.50}
    result = compute_statistical_parity(rates)

    overall = (0.40 + 0.60 + 0.50) / 3
    sc = next(c for c in result["categories"] if c["category"] == "sc")
    ur = next(c for c in result["categories"] if c["category"] == "ur")

    assert abs(sc["deviation"] - (0.40 - overall)) < 1e-9
    assert abs(ur["deviation"] - (0.60 - overall)) < 1e-9


def test_statistical_parity_max_disparity():
    rates = {"sc": 0.40, "ur": 0.60, "obc": 0.50}
    result = compute_statistical_parity(rates)

    overall = (0.40 + 0.60 + 0.50) / 3
    expected_max = max(abs(0.40 - overall), abs(0.60 - overall), abs(0.50 - overall))
    assert abs(result["max_disparity"] - expected_max) < 1e-9


def test_statistical_parity_min_max():
    rates = {"sc": 0.30, "ur": 0.70, "obc": 0.50}
    result = compute_statistical_parity(rates)

    assert result["min_rate"] == 0.30
    assert result["max_rate"] == 0.70


def test_statistical_parity_empty():
    result = compute_statistical_parity({})
    assert result["overall_rate"] == 0.0
    assert result["max_disparity"] == 0.0


# ── Prompt Sanitisation ─────────────────────────────────────────────────────


def test_sanitize_strips_name_and_demographic_fields():
    resume = {
        "name": "Asha Devi",
        "first_name": "Asha",
        "last_name": "Devi",
        "gender": "female",
        "date_of_birth": "1995-06-15",
        "caste": "SC",
        "religion": "Hindu",
        "phone": "9876543210",
        "email": "asha@example.com",
        "aadhaar": "123456789012",
        "skills": ["Python", "AutoCAD"],
        "education": [{"degree": "B.Tech", "year": 2017}],
        "total_experience_years": 5,
    }
    clean = sanitize_resume_for_prompt(resume)

    # Demographic fields removed
    for key in ("name", "first_name", "last_name", "gender", "date_of_birth",
                "caste", "religion", "phone", "email", "aadhaar"):
        assert key not in clean, f"{key!r} should be stripped"

    # Professional fields preserved
    assert clean["skills"] == ["Python", "AutoCAD"]
    assert clean["total_experience_years"] == 5
    assert clean["education"][0]["degree"] == "B.Tech"


def test_sanitize_does_not_mutate_original():
    resume = {"name": "Test", "skills": ["Java"]}
    _ = sanitize_resume_for_prompt(resume)
    assert "name" in resume  # original unchanged


def test_sanitize_handles_nested_dicts():
    resume = {
        "personal": {"name": "X", "gender": "male"},
        "skills": ["Go"],
    }
    clean = sanitize_resume_for_prompt(resume)
    assert "name" not in clean["personal"]
    assert "gender" not in clean["personal"]
    assert clean["skills"] == ["Go"]


def test_sanitize_handles_non_dict_input():
    assert sanitize_resume_for_prompt(None) is None
    assert sanitize_resume_for_prompt("text") == "text"
