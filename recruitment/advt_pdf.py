"""Generate a clean, readable advertisement PDF matching the NEEPCO layout.

Uses fpdf2 with Arial TTF (regular + bold). Features a centred company header,
coloured section bars, boxed per-post blocks with key/value rows, the online
registration schedule, boilerplate sections, and a page footer with the
advertisement number and page number.
"""

import os

from .boilerplate import DEFAULT_COMPANY_PROFILE, DEFAULT_HOW_TO_APPLY

try:
    from fpdf import FPDF
except ImportError:  # pragma: no cover
    FPDF = None

# Brand palette
COLOR_PRIMARY = (76, 102, 240)      # indigo
COLOR_DARK = (26, 27, 46)           # near-black ink
COLOR_TEXT = (48, 48, 64)           # body text
COLOR_MUTED = (112, 112, 132)       # labels / secondary
COLOR_LIGHT = (243, 244, 252)       # zebra / box fill
COLOR_WHITE = (255, 255, 255)

MARGIN = 16


def _fmt_date(value):
    return value.strftime("%d-%m-%Y") if value else ""


def _num_words(n):
    words = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
             6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}
    return words.get(n, str(n))


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


class AdvtPDF(FPDF):
    """A4 advertisement PDF with helpers for the structured layout."""

    def __init__(self, advt_number=""):
        super().__init__(format="A4", unit="mm")
        self._advt_number = advt_number
        reg, bld = _font_paths()
        self._font_ok = reg is not None
        if reg:
            self.add_font("advt", "", reg)
            if bld:
                self.add_font("advt", "B", bld)
        self.set_margins(MARGIN, 18, MARGIN)
        self.set_auto_page_break(auto=True, margin=22)
        self.add_page()

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(200, 202, 224)
        self.set_line_width(0.3)
        self.line(MARGIN, self.get_y(), self.w - MARGIN, self.get_y())
        self.set_y(-12)
        self._set_f("", 8)
        self.set_text_color(*COLOR_MUTED)
        left = f"Advertisement No: {self._advt_number}"
        right = f"Page {self.page_no()}"
        left_w = self.get_string_width(left)
        right_w = self.get_string_width(right)
        self.set_xy(MARGIN, self.get_y())
        self.cell(left_w, 5, left)
        self.set_x(self.w - MARGIN - right_w)
        self.cell(right_w, 5, right)

    def _set_f(self, style="", size=9.5):
        if self._font_ok:
            self.set_font("advt", style, size)
        else:
            self.set_font("helvetica", style, size)

    def _mc(self, text, align="L", size=None):
        """multi_cell that resets the cursor to the left margin afterwards."""
        if size:
            self._set_f("", size)
        self.multi_cell(0, 5.4, text, align=align)
        self.set_x(self.l_margin)

    def _section(self, title):
        self.ln(4)
        self._set_f("B", 11)
        self.set_fill_color(*COLOR_PRIMARY)
        self.set_text_color(*COLOR_WHITE)
        self.cell(0, 9, f"  {title}", fill=True)
        self.ln(11)
        self.set_text_color(*COLOR_TEXT)
        self._set_f("", 9.5)

    def _para(self, text):
        self._set_f("", 9.5)
        self.set_text_color(*COLOR_TEXT)
        for i, para in enumerate(text.strip().split("\n\n")):
            if i:
                self.ln(2)
            self._mc(para.strip(), align="J")
        self.ln(2)

    def _kv(self, key, value):
        label_w = 46
        self._set_f("B", 9)
        self.set_text_color(*COLOR_MUTED)
        y = self.get_y()
        self.cell(label_w, 5.4, key, ln=0)
        self.set_text_color(*COLOR_TEXT)
        self._set_f("", 9.5)
        self.set_xy(MARGIN + label_w, y)
        self._mc(value, align="L")

    def _post_block(self, idx, post, advt):
        breakups = post.category_breakup_display or f"UR-{post.vacancies}"
        start_y = self.get_y()

        self._set_f("B", 10)
        self.set_text_color(*COLOR_DARK)
        self._mc(f"{idx}. Name of the Post: {post.name}")
        self._set_f("B", 8.5)
        self.set_text_color(*COLOR_PRIMARY)
        self._mc(f"Post Code: {post.post_code}")
        self.set_text_color(*COLOR_TEXT)
        self._set_f("", 9.5)
        self.ln(1)

        self._kv("No. of Posts", f"{_num_words(post.vacancies)} ({breakups})")
        if post.max_age:
            self._kv("Maximum Age", f"{post.max_age} years as on {_fmt_date(advt.closing_date)}")
        if post.period_of_engagement:
            self._kv("Engagement", post.period_of_engagement)
        self._kv("Qualification", post.qualification or "—")
        if post.experience_required:
            self._kv("Experience", post.experience_required)
        if post.pay_scale:
            self._kv("Remuneration", f"Consolidated minimum monthly compensation will be {post.pay_scale}")
            self._kv("Benefits", "HRA or Company Accommodation and medical facility for self, spouse, 2 children and dependent parents.")
        if post.location:
            self._kv("Location", post.location)

        end_y = self.get_y() + 3
        self.set_draw_color(214, 216, 236)
        self.set_line_width(0.3)
        self.rect(MARGIN, start_y - 2, self.w - 2 * MARGIN, end_y - start_y + 2)
        self.ln(5)


def generate_advertisement_pdf(advt):
    """Return bytes of a formatted, readable advertisement PDF."""
    if FPDF is None:
        raise RuntimeError("fpdf2 not installed.")

    pdf = AdvtPDF(advt_number=advt.advt_number)

    from .org_profile import get_org_profile

    org = get_org_profile()

    # ---- Header ----
    pdf._set_f("B", 16)
    pdf.set_text_color(*COLOR_DARK)
    pdf._mc(org.name_en or "North Eastern Electric Power Corporation Limited", align="C")
    pdf._set_f("", 10)
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf._mc(org.tagline_en or "(A Government of India Enterprise)", align="C")
    pdf._set_f("", 8.5)
    pdf.set_text_color(*COLOR_MUTED)
    if org.address:
        pdf._mc(org.address, align="C")
    pdf.ln(2)
    pdf.set_draw_color(*COLOR_PRIMARY)
    pdf.set_line_width(0.6)
    pdf.line(MARGIN, pdf.get_y(), pdf.w - MARGIN, pdf.get_y())
    pdf.ln(4)
    pdf._set_f("", 9.5)
    pdf.set_text_color(*COLOR_TEXT)
    pdf._mc(f"Date: {_fmt_date(advt.published_date)}    Advertisement No: {advt.advt_number}", align="C")
    pdf.ln(3)

    # ---- Company profile ----
    pdf._section("COMPANY PROFILE")
    pdf._para(advt.description or DEFAULT_COMPANY_PROFILE)
    pdf._set_f("B", 11)
    pdf.set_text_color(*COLOR_DARK)
    pdf._mc(advt.title.upper(), align="C")
    pdf.ln(2)
    pdf._set_f("", 9.5)
    pdf.set_text_color(*COLOR_TEXT)
    pdf._mc("NEEPCO is looking for experienced professionals on Fixed Term Basis, as per details given below:")
    pdf.ln(3)

    # ---- Posts ----
    pdf._section("DETAILS OF POSTS")
    for idx, post in enumerate(advt.posts.all(), start=1):
        pdf._post_block(idx, post, advt)

    # ---- Schedule ----
    pdf._section("SCHEDULE OF ONLINE REGISTRATION")
    pdf._kv("Advertisement No", advt.advt_number)
    pdf._kv("Commencement of Online Registration", _fmt_date(advt.published_date))
    pdf._kv("Closing of Online Registration", _fmt_date(advt.closing_date))
    pdf.ln(2)

    # ---- Boilerplate ----
    pdf._section("HEALTH")
    pdf._para(advt.health_text or "The candidate should have sound health. Before joining, candidates will have to undergo medical examination and obtain a medical certificate stating medical fitness.")

    pdf._section("GENERAL CONDITIONS")
    pdf._para(advt.general_conditions or "As per company recruitment rules.")

    pdf._section("HOW TO APPLY")
    pdf._para(advt.how_to_apply or DEFAULT_HOW_TO_APPLY)

    if org.sbi_epay_text:
        pdf._section("REGISTRATION FEES")
        pdf._para(org.sbi_epay_text)

    if org.contact_email:
        pdf.ln(2)
        pdf._set_f("", 9.5)
        pdf.set_text_color(*COLOR_TEXT)
        pdf._mc(f"Contact e-mail ID of Recruitment Cell: {org.contact_email}")

    return bytes(pdf.output(dest="S"))
