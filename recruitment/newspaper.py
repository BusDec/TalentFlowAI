"""Generate Employment News / national-newspaper formatted ad text (Phase 4, Task 3).

Produces a compact, column-friendly plain-text advertisement suitable for
publication in Employment News, national dailies, or regional newspapers.
The format mirrors the standard layout used by Indian PSUs (NEEPCO, THDC,
NHPC, etc.) when advertising in Employment News:

  1. Org name header (centred, uppercase)
  2. Address / tagline
  3. Advertisement number + date
  4. Post table: code, name, vacancies (with category breakup), pay, age, qual
  5. How-to-apply summary
  6. Important dates
  7. Footer / disclaimer

The function is a pure text builder — no DB writes, no file I/O.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from recruitment.models import Advertisement


def _fmt_date(value) -> str:
    """Format a date or date-string as DD-MM-YYYY."""
    if isinstance(value, str):
        try:
            value = datetime.date.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%d-%m-%Y") if value else ""


def _num_words(n: int) -> str:
    """Return English word for small numbers (1-10), else the digit string."""
    words = {
        1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
        6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten",
    }
    return words.get(n, str(n))


# ── Column widths for the post table ────────────────────────────────────────
_COL_CODE = 12
_COL_POST = 28
_COL_VAC = 18
_COL_PAY = 20
_COL_AGE = 14
_COL_QUAL = 32


def _pad(text: str, width: int) -> str:
    """Pad *text* to exactly *width* characters (truncates if longer)."""
    return text[:width].ljust(width)


def _header_row() -> str:
    """Column-header line for the post table."""
    return (
        f"{_pad('Post Code', _COL_CODE)}"
        f"{_pad('Name of Post', _COL_POST)}"
        f"{_pad('Vacancies', _COL_VAC)}"
        f"{_pad('Pay Scale / CTC', _COL_PAY)}"
        f"{_pad('Max Age', _COL_AGE)}"
        f"Qualification"
    )


def _separator() -> str:
    return "-" * (_COL_CODE + _COL_POST + _COL_VAC + _COL_PAY + _COL_AGE + 15)


def _post_row(post) -> str:
    """One data row for the post table."""
    breakups = post.category_breakup_display or f"UR-{post.vacancies}"
    vac_text = f"{_num_words(post.vacancies)} ({breakups})"
    age_text = f"{post.max_age} yrs" if post.max_age else "—"
    pay_text = post.pay_scale or "As per rules"
    qual_text = (post.qualification or "").replace("\n", "; ")
    return (
        f"{_pad(post.post_code, _COL_CODE)}"
        f"{_pad(post.name, _COL_POST)}"
        f"{_pad(vac_text, _COL_VAC)}"
        f"{_pad(pay_text, _COL_PAY)}"
        f"{_pad(age_text, _COL_AGE)}"
        f"{qual_text}"
    )


def generate_newspaper_text(advt: "Advertisement") -> str:
    """Return Employment News formatted plain text for *advt*.

    Args:
        advt: An ``Advertisement`` instance with prefetched ``posts``.

    Returns:
        A multi-line string ready for newspaper submission or preview.
    """
    from .org_profile import get_org_profile

    org = get_org_profile()
    lines: list[str] = []

    # ── 1. Org header ────────────────────────────────────────────────────
    name = (org.name_en or "Organisation").upper()
    lines.append(name.center(80))
    if org.tagline_en:
        lines.append(org.tagline_en.center(80))
    if org.address:
        # Wrap address to keep column width manageable
        for addr_line in org.address.splitlines():
            lines.append(addr_line.strip().center(80))
    lines.append("")

    # ── 2. Advt number + date ────────────────────────────────────────────
    lines.append(
        f"Advertisement No. {advt.advt_number}    "
        f"Date: {_fmt_date(advt.published_date)}"
    )
    lines.append("")

    # ── 3. Title / subject ───────────────────────────────────────────────
    lines.append(advt.title.upper().center(80))
    lines.append("")

    # ── 4. Brief description ─────────────────────────────────────────────
    if advt.description:
        # First paragraph / first 300 chars for compactness
        desc = advt.description.strip()
        if len(desc) > 400:
            desc = desc[:397] + "..."
        lines.append(desc)
        lines.append("")

    # ── 5. Post table ────────────────────────────────────────────────────
    posts = list(advt.posts.all().order_by("name"))
    if posts:
        lines.append(_header_row())
        lines.append(_separator())
        for post in posts:
            lines.append(_post_row(post))
        lines.append(_separator())
        total = sum(p.vacancies for p in posts)
        lines.append(f"Total Vacancies: {_num_words(total)} ({total})")
        lines.append("")

        # ── 5a. Per-post detail blocks ───────────────────────────────────
        for idx, post in enumerate(posts, start=1):
            lines.append(f"{idx}. {post.name} ({post.post_code})")
            if post.qualification:
                lines.append(f"   Qualification: {post.qualification}")
            if post.experience_required:
                lines.append(f"   Experience: {post.experience_required}")
            if post.max_age:
                lines.append(f"   Age Limit: {post.max_age} years as on {_fmt_date(advt.closing_date)}")
            if post.pay_scale:
                lines.append(f"   Pay: {post.pay_scale}")
            if post.location:
                lines.append(f"   Location: {post.location}")
            if post.period_of_engagement:
                lines.append(f"   Period: {post.period_of_engagement}")
            lines.append("")

    # ── 6. How to apply ──────────────────────────────────────────────────
    apply_text = (advt.how_to_apply or "").strip()
    if apply_text:
        lines.append("HOW TO APPLY:")
        lines.append(apply_text if len(apply_text) <= 300 else apply_text[:297] + "...")
        lines.append("")

    # ── 7. Important dates ───────────────────────────────────────────────
    lines.append("IMPORTANT DATES:")
    lines.append(f"  Opening Date for Online Application: {_fmt_date(advt.published_date)}")
    lines.append(f"  Closing Date for Online Application: {_fmt_date(advt.closing_date)}")
    lines.append("")

    # ── 8. Registration fee ──────────────────────────────────────────────
    if org.sbi_epay_text:
        lines.append("APPLICATION FEE:")
        fee = org.sbi_epay_text.strip()
        lines.append(fee if len(fee) <= 200 else fee[:197] + "...")
        lines.append("")

    # ── 9. Contact / footer ──────────────────────────────────────────────
    if org.contact_email:
        lines.append(f"Contact: {org.contact_email}")
    if org.website:
        lines.append(f"Website: {org.website}")
    lines.append("")

    # Disclaimer
    lines.append(
        "For detailed information including eligibility criteria, category-wise "
        "vacancies, and general conditions, please visit the organisation website "
        "or refer to the detailed advertisement."
    )

    return "\n".join(lines)
