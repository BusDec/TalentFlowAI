"""Generate a plain A4 offer letter PDF for a candidate application.

Plain govt-format style (black text, thin rules, single column) matching the
advertisement and application-slip PDFs: OrgProfile letterhead, an
"OFFER OF APPOINTMENT" title, a Reference No / Date block, candidate name +
address (CandidateProfile.permanent_address when present), the numbered offer
terms drawn from the Post fields, a joining-document checklist, acceptance
instructions, an Authorised Signatory signature block with a digital-signature
placeholder, and a footer of motto + "Page X of Y".

Interface: ``OfferPDF(application).generate() -> bytes``.
"""

import datetime
import os

try:
    from fpdf import FPDF
except ImportError:  # pragma: no cover
    FPDF = None

# Plain govt palette: near-black ink, grey labels, thin rules.
INK = (20, 20, 24)
MUTED = (80, 80, 90)
RULE = (150, 150, 160)

MARGIN = 18

# Joining-time documents every appointee must furnish (spec §3).
DOC_CHECKLIST = [
    "Identity proof (Aadhaar / PAN / Voter ID / Passport)",
    "Educational qualification certificates (original)",
    "Experience certificates",
    "Medical fitness certificate",
]

ACCEPTANCE_TEXT = (
    "Please communicate your acceptance of this offer within 15 days of "
    "receipt of this letter."
)

PROOF_TEXT = (
    "You will be required to furnish satisfactory proof of identity, age, "
    "qualifications and medical fitness before joining."
)


def _font_paths():
    regular = [
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    bold = [
        r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    reg = next((p for p in regular if os.path.exists(p)), None)
    bld = next((p for p in bold if os.path.exists(p)), None)
    return reg, bld


def _fmt_date(value):
    return value.strftime("%d-%m-%Y") if value else ""


class OfferPDF(FPDF):
    """A4 offer letter with letterhead, offer terms and signature block."""

    def __init__(self, application):
        super().__init__(format="A4", unit="mm")
        self._application = application
        from .org_profile import get_org_profile

        self.org = get_org_profile()
        reg, bld = _font_paths()
        self._font_ok = reg is not None
        if reg:
            self.add_font("offer", "", reg)
            if bld:
                self.add_font("offer", "B", bld)
        self.set_margins(MARGIN, 18, MARGIN)
        self.set_auto_page_break(auto=True, margin=24)
        self.alias_nb_pages()
        self.add_page()

    def footer(self):
        """Motto + Page X of Y on every page."""
        self.set_y(-15)
        self._set_f("", 8)
        self.set_text_color(*MUTED)
        self.cell(
            0,
            10,
            f"{self.org.footer_motto}  |  Page {self.page_no()} of {{nb}}",
            align="C",
        )

    def _set_f(self, style="", size=9.5):
        if self._font_ok:
            self.set_font("offer", style, size)
        else:
            self.set_font("helvetica", style, size)

    def _mc(self, text, align="L", size=None):
        """multi_cell that resets the cursor to the left margin afterwards."""
        if size:
            self._set_f("", size)
        self.multi_cell(0, 5.4, text, align=align)
        self.set_x(self.l_margin)

    def generate(self):
        """Return bytes of the formatted offer letter."""
        if FPDF is None:
            raise RuntimeError("fpdf2 not installed.")

        application = self._application
        cand = application.candidate
        post = application.post

        # ---- Letterhead ----
        if self.org.name_hi:
            self._set_f("B", 14)
            self.set_text_color(*INK)
            self._mc(self.org.name_hi, align="C")
        self._set_f("B", 13 if self.org.name_hi else 16)
        self.set_text_color(*INK)
        self._mc(self.org.name_en or "Organisation", align="C")
        if self.org.tagline_en:
            self._set_f("", 10)
            self.set_text_color(*INK)
            self._mc(self.org.tagline_en, align="C")
        if self.org.address:
            self._set_f("", 8.5)
            self.set_text_color(*MUTED)
            self._mc(self.org.address, align="C")
        self.ln(2)
        self.set_draw_color(*RULE)
        self.set_line_width(0.6)
        self.line(MARGIN, self.get_y(), self.w - MARGIN, self.get_y())
        self.ln(5)

        # ---- Title ----
        self._set_f("B", 13)
        self.set_text_color(*INK)
        self._mc("OFFER OF APPOINTMENT", align="C")
        self.ln(4)

        # ---- Reference / date ----
        self._set_f("", 10)
        self.set_text_color(*INK)
        self._mc(
            f"Reference No: {post.advertisement.advt_number}-"
            f"{application.application_id}-{datetime.date.today().year}"
        )
        self._mc(f"Date: {_fmt_date(datetime.date.today())}")
        self.ln(4)

        # ---- Candidate block ----
        profile = getattr(cand, "profile", None)
        address = profile.permanent_address if profile is not None else ""
        self._mc(f"Dear {cand.first_name} {cand.last_name},")
        if address:
            self._mc(address)
        self.ln(3)

        self._mc(
            f"With reference to your application for the post of {post.name} "
            f"against Advertisement No. {post.advertisement.advt_number}, we are "
            "pleased to offer you appointment on Fixed Term Basis on the "
            "following terms:"
        )
        self.ln(2)

        # ---- Offer terms (from the post fields) ----
        terms = [
            f"1. Post: {post.name}",
            f"2. Post Code: {post.post_code}",
            f"3. Remuneration: {post.pay_scale or 'As per company policy'} "
            "(consolidated) plus HRA or Company Accommodation and medical "
            "facility as per policy.",
            "4. Place of Posting: "
            + (
                post.location
                or "Shillong or any Office/Project site of NEEPCO as per "
                "management discretion."
            )
            + ".",
            "5. Period of Engagement: "
            + (
                post.period_of_engagement
                or "Initially for 3 (three) years and extendable by further 2 "
                "(two) years on yearly basis based on the performance and "
                "requirement."
            )
            + ".",
            "6. Probation: As per company rules.",
            f"7. {PROOF_TEXT}",
        ]
        for term in terms:
            self._mc(term)
            self.ln(1.4)
        self.ln(3)

        # ---- Document checklist ----
        self._set_f("B", 10.5)
        self.set_text_color(*INK)
        self._mc("DOCUMENTS TO BE FURNISHED AT THE TIME OF JOINING")
        self.ln(2)
        self._set_f("", 9.5)
        self.set_text_color(*INK)
        for doc in DOC_CHECKLIST:
            self._mc(f"\u2022 {doc}")
            self.ln(1)
        self.ln(3)

        # ---- Acceptance instructions ----
        self._set_f("", 10)
        self.set_text_color(*INK)
        self._mc(ACCEPTANCE_TEXT)
        self.ln(8)

        # ---- Signature block ----
        self._set_f("", 10)
        self.set_text_color(*INK)
        self._mc("Yours faithfully,", align="R")
        self._mc(f"For {self.org.name_en}", align="R")
        self.ln(8)
        self._set_f("", 10)
        self._mc("(Authorised Signatory)", align="R")
        self._set_f("", 9)
        self.set_text_color(*MUTED)
        self._mc("Digitally signed copy to follow.", align="R")

        return bytes(self.output(dest="S"))
