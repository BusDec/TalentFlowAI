"""Generate a plain A4 application slip PDF for a candidate application.

Plain govt-format style (black text, thin rules, single column) matching the
advertisement PDF: OrgProfile letterhead, an "APPLICATION SLIP" title, key/
value rows for the application, a deterministic fee-status line, a document
checklist, and a footer carrying the mandatory "No document is required to be
sent by post." line plus "Page X of Y" numbering.

Interface: ``ApplicationSlipPDF(application).generate() -> bytes``.
"""

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

# Fee exemption rule (docs/superpowers/specs/2026-08-08-slip-pdf-design.md):
# SC/ST/PwBD/ESM category and female candidates are exempt from the
# application fee. No payment gateway exists yet, so the status is computed
# deterministically from the candidate profile.
EXEMPT_CATEGORIES = {"sc", "st"}
FEE_EXEMPT_TEXT = "Exempted (SC/ST/PwBD/Female)"
FEE_PAYABLE_TEXT = "To be paid - Rs 500/- (online)"

FOOTER_TEXT = "No document is required to be sent by post."


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


def _fee_status(application):
    """Fee status for an application (never raises).

    Consults the Payment row if one exists — returns the actual payment
    status (paid / exempt / failed / pending).  Falls back to deterministic
    profile-based check when no Payment record is present.
    """
    # Prefer Payment row when it exists.
    try:
        payment = application.payment
    except Exception:
        payment = None

    if payment is not None:
        if payment.exempt:
            return FEE_EXEMPT_TEXT
        if payment.status == "completed":
            return f"Paid — Rs {payment.amount:.0f}/-"
        if payment.status == "failed":
            return "Payment failed — please retry"
        # pending
        return FEE_PAYABLE_TEXT

    # Fallback: deterministic profile-based check.
    profile = getattr(application.candidate, "profile", None)
    if profile is not None:
        if (
            profile.category in EXEMPT_CATEGORIES
            or profile.is_pwbd
            or profile.gender == "F"
        ):
            return FEE_EXEMPT_TEXT
    return FEE_PAYABLE_TEXT


class ApplicationSlipPDF(FPDF):
    """A4 application slip with letterhead, key/value rows and a footer."""

    def __init__(self, application):
        super().__init__(format="A4", unit="mm")
        self._application = application
        reg, bld = _font_paths()
        self._font_ok = reg is not None
        if reg:
            self.add_font("slip", "", reg)
            if bld:
                self.add_font("slip", "B", bld)
        self.set_margins(MARGIN, 18, MARGIN)
        self.set_auto_page_break(auto=True, margin=24)
        self.alias_nb_pages()
        self.add_page()

    def footer(self):
        self.set_y(-16)
        self.set_draw_color(*RULE)
        self.set_line_width(0.3)
        self.line(MARGIN, self.get_y(), self.w - MARGIN, self.get_y())
        self.set_y(-14)
        self._set_f("", 8)
        self.set_text_color(*MUTED)
        left = FOOTER_TEXT
        right = f"Page {self.page_no()} of {{nb}}"
        left_w = self.get_string_width(left)
        right_w = self.get_string_width(right)
        self.set_xy(MARGIN, self.get_y())
        self.cell(left_w, 5, left)
        self.set_x(self.w - MARGIN - right_w)
        self.cell(right_w, 5, right)

    def _set_f(self, style="", size=9.5):
        if self._font_ok:
            self.set_font("slip", style, size)
        else:
            self.set_font("helvetica", style, size)

    def _mc(self, text, align="L", size=None):
        """multi_cell that resets the cursor to the left margin afterwards."""
        if size:
            self._set_f("", size)
        self.multi_cell(0, 5.4, text, align=align)
        self.set_x(self.l_margin)

    def _kv(self, key, value):
        label_w = 52
        self._set_f("B", 9)
        self.set_text_color(*MUTED)
        y = self.get_y()
        self.cell(label_w, 5.8, key, ln=0)
        self.set_text_color(*INK)
        self._set_f("", 9.5)
        self.set_xy(MARGIN + label_w, y)
        self._mc(value, align="L")

    def generate(self):
        """Return bytes of the formatted application slip."""
        if FPDF is None:
            raise RuntimeError("fpdf2 not installed.")

        application = self._application
        from .org_profile import get_org_profile

        org = get_org_profile()

        # ---- Letterhead ----
        if org.name_hi:
            self._set_f("B", 14)
            self.set_text_color(*INK)
            self._mc(org.name_hi, align="C")
        self._set_f("B", 13 if org.name_hi else 16)
        self.set_text_color(*INK)
        self._mc(org.name_en or "Organisation", align="C")
        if org.tagline_en:
            self._set_f("", 10)
            self.set_text_color(*INK)
            self._mc(org.tagline_en, align="C")
        if org.address:
            self._set_f("", 8.5)
            self.set_text_color(*MUTED)
            self._mc(org.address, align="C")
        self.ln(2)
        self.set_draw_color(*RULE)
        self.set_line_width(0.6)
        self.line(MARGIN, self.get_y(), self.w - MARGIN, self.get_y())
        self.ln(5)

        # ---- Title ----
        self._set_f("B", 13)
        self.set_text_color(*INK)
        self._mc("APPLICATION SLIP", align="C")
        self.ln(4)

        # ---- Key/value rows ----
        post = application.post
        candidate = application.candidate
        self._kv("Application ID", application.application_id)
        self._kv("Advertisement No", post.advertisement.advt_number)
        self._kv("Post", f"{post.name} ({post.post_code})")
        self._kv(
            "Candidate Name",
            f"{candidate.first_name} {candidate.last_name}".strip(),
        )
        self._kv("Date of Application", _fmt_date(application.applied_at))
        self._kv("Application Status", application.get_status_display())
        self._kv("Fee Status", _fee_status(application))
        self.ln(3)

        # ---- Document checklist ----
        self._set_f("B", 10.5)
        self.set_text_color(*INK)
        self._mc("DOCUMENTS UPLOADED")
        self.ln(2)
        docs = list(application.documents.all())
        if not docs:
            self._set_f("", 9.5)
            self.set_text_color(*INK)
            self._mc("No documents uploaded.")
            self.ln(2)
        for doc in docs:
            self._set_f("", 9.5)
            self.set_text_color(*INK)
            label = doc.doc_type
            extracted_data = doc.extracted_data if isinstance(doc.extracted_data, dict) else {}
            extracted = extracted_data.get("doc_type")
            if extracted and extracted != doc.doc_type:
                label = f"{label} (extracted: {extracted})"
            self._mc(f"\u2022 {label} \u2014 Uploaded: Yes", align="L")
            self.ln(1)
        self.ln(2)

        return bytes(self.output(dest="S"))
