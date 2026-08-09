"""Employment News format text generation tests (Phase 4, Task 3)."""

import pytest

from recruitment.models import Advertisement, Post
from recruitment.newspaper import generate_newspaper_text
from recruitment.org_profile import get_org_profile


@pytest.fixture
def _org(tenant):
    """Ensure OrgProfile has recognisable fields for assertions."""
    org = get_org_profile()
    org.name_en = "North Eastern Electric Power Corporation Limited"
    org.tagline_en = "(A Government of India Enterprise)"
    org.address = "Brookland Compound, Lower Mawblei, Shillong – 793002"
    org.contact_email = "recruitment@neepco.in"
    org.website = "https://www.neepco.co.in"
    org.save()
    return org


# ── Core acceptance: output contains org name + post codes ──────────────────


def test_contains_org_name(tenant, advertisement, _org):
    """Newspaper text must include the organisation name."""
    text = generate_newspaper_text(advertisement)
    assert "NORTH EASTERN ELECTRIC POWER CORPORATION LIMITED" in text


def test_contains_post_codes(tenant, advertisement, _org):
    """Newspaper text must include every post code from the advertisement."""
    text = generate_newspaper_text(advertisement)
    for post in advertisement.posts.all():
        assert post.post_code in text


def test_contains_post_names(tenant, advertisement, _org):
    """Newspaper text must include post names."""
    text = generate_newspaper_text(advertisement)
    for post in advertisement.posts.all():
        assert post.name in text


# ── Structural checks ───────────────────────────────────────────────────────


def test_contains_advt_number(tenant, advertisement, _org):
    text = generate_newspaper_text(advertisement)
    assert advertisement.advt_number in text


def test_contains_advt_title(tenant, advertisement, _org):
    """Title is uppercased in the output."""
    text = generate_newspaper_text(advertisement)
    assert advertisement.title.upper() in text


def test_contains_important_dates(tenant, advertisement, _org):
    text = generate_newspaper_text(advertisement)
    assert "IMPORTANT DATES" in text
    assert "Opening Date" in text
    assert "Closing Date" in text


def test_contains_total_vacancies(tenant, advertisement, _org):
    text = generate_newspaper_text(advertisement)
    assert "Total Vacancies" in text


def test_contains_how_to_apply(tenant, advertisement, _org):
    """When how_to_apply is set, the section header appears."""
    advertisement.how_to_apply = "Apply online through our portal."
    advertisement.save()
    text = generate_newspaper_text(advertisement)
    assert "HOW TO APPLY" in text
    assert "Apply online" in text


def test_contains_contact_email(tenant, advertisement, _org):
    text = generate_newspaper_text(advertisement)
    assert "recruitment@neepco.in" in text


def test_contains_website(tenant, advertisement, _org):
    text = generate_newspaper_text(advertisement)
    assert "https://www.neepco.co.in" in text


def test_disclaimer_present(tenant, advertisement, _org):
    text = generate_newspaper_text(advertisement)
    assert "detailed information" in text.lower() or "eligibility criteria" in text.lower()


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_no_posts_still_produces_output(tenant, _org):
    """An advertisement with zero posts should still generate valid text."""
    advt = Advertisement.objects.create(
        advt_number="EMPTY/01/2026",
        title="No Posts Advt",
        published_date="2026-03-01",
        closing_date="2026-04-01",
    )
    text = generate_newspaper_text(advt)
    assert "EMPTY/01/2026" in text
    assert "NO POSTS ADVT" in text
    # Should not crash, just omit the post table
    assert "Total Vacancies" not in text


def test_description_truncation(tenant, _org):
    """Very long descriptions get truncated to ~400 chars."""
    advt = Advertisement.objects.create(
        advt_number="LONG/01/2026",
        title="Long Description",
        published_date="2026-01-01",
        closing_date="2026-12-31",
        description="X" * 1000,
    )
    text = generate_newspaper_text(advt)
    # The truncated block should appear, not the full 1000-char string
    assert "XXX..." in text
    assert "X" * 500 not in text


def test_tagline_centered(tenant, advertisement, _org):
    """Tagline should appear in the output (centering is whitespace-only)."""
    text = generate_newspaper_text(advertisement)
    assert "(A Government of India Enterprise)" in text


def test_category_breakup_in_table(tenant, advertisement, _org):
    """Category breakup from the post should appear in the table row."""
    text = generate_newspaper_text(advertisement)
    # The fixture creates posts with category_breakup={"ur": 1}
    assert "UR-1" in text


def test_pay_scale_in_detail_block(tenant, advertisement, _org):
    """When pay_scale is set, it appears in the per-post detail block."""
    post = advertisement.posts.first()
    post.pay_scale = "Rs. 60,000-1,80,000"
    post.save()
    text = generate_newspaper_text(advertisement)
    assert "Rs. 60,000-1,80,000" in text


def test_fee_section_when_present(tenant, advertisement, _org):
    """Application fee section appears when sbi_epay_text is set."""
    org = get_org_profile()
    org.sbi_epay_text = "General/OBC: Rs. 500/-; SC/ST/PwBD: Nil"
    org.save()
    text = generate_newspaper_text(advertisement)
    assert "APPLICATION FEE" in text
    assert "Rs. 500/-" in text


def test_return_type_is_str(tenant, advertisement, _org):
    """generate_newspaper_text must return a plain string."""
    result = generate_newspaper_text(advertisement)
    assert isinstance(result, str)
    assert len(result) > 100
