"""Generate a plain govt-format advertisement PDF (Phase 2, Task 1).

Plain black A4 layout driven by OrgProfile + Advertisement data: centred
letterhead (name_hi over name_en, tagline, address), date / advertisement
number lines, COMPANY PROFILE, per-post label:value rows, HEALTH / GENERAL
CONDITIONS / HOW TO APPLY boilerplate (with the SBI ePay fee text folded
into HOW TO APPLY), the online REGISTRATION SCHEDULE table, a contact line,
and a footer of motto + "Page X of Y".

Bullets use cp1252-safe `•` / `-` — the `➢`/`❖` glyphs are not in the core
font, so `_para` strips them (documented deviation; kills the missing-glyph
warning in the dev logs).
"""

import datetime
import os

from .boilerplate import (
    DEFAULT_COMPANY_PROFILE,
    DEFAULT_GENERAL_CONDITIONS,
    DEFAULT_HEALTH_TEXT,
    DEFAULT_HOW_TO_APPLY,
)
from .org_profile import get_org_profile

try:
    from fpdf import FPDF
except ImportError:  # pragma: no cover
    FPDF = None

# Plain govt format: black ink, thin 0.4mm rules, no colour bars/boxes.
MARGIN = 18  # mm on A4 portrait
BLACK = (0, 0, 0)


def _fmt_date(value):
    if isinstance(value, str):
        try:
            value = datetime.date.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%d-%m-%Y") if value else ""


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
    """A4 govt-format advertisement PDF, plain black on white."""

    def __init__(self, advt):
        super().__init__(format="A4", unit="mm")
        self.advt = advt
        self.org = get_org_profile()
        reg, bld = _font_paths()
        self._font_ok = reg is not None
        if reg:
            self.add_font("advt", "", reg)
            if bld:
                self.add_font("advt", "B", bld)
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(auto=True, margin=22)
        self.alias_nb_pages()
        self.add_page()

    # -- low-level helpers ------------------------------------------------

    def _set_f(self, style="", size=9.5):
        if self._font_ok:
            self.set_font("advt", style, size)
        else:
            self.set_font("helvetica", style, size)

    def _mc(self, text, align="L"):
        """multi_cell that resets the cursor to the left margin afterwards."""
        self.multi_cell(0, 5.4, text, align=align)
        self.set_x(self.l_margin)

    def _rule(self):
        """Thin 0.4mm black rule across the text column."""
        y = self.get_y()
        self.set_draw_color(*BLACK)
        self.set_line_width(0.4)
        self.line(self.l_margin, y, self.w - self.r_margin, y)

    def _center(self, text, size, style="", color=BLACK):
        """Centred letterhead line (black by default)."""
        self._set_f(style, size)
        self.set_text_color(*color)
        self._mc(text, align="C")

    def _section(self, title):
        """Bold 11 section heading followed by a thin rule."""
        self.ln(4)
        self._set_f("B", 11)
        self.set_text_color(*BLACK)
        self.cell(0, 7, title)
        self.ln(7)
        self._rule()
        self.ln(4)
        self._set_f("", 9.5)

    def _kv(self, label, value):
        """label:value row — bold label column, wrapped value beside it."""
        label_w = 46
        self._set_f("B", 9.5)
        self.set_text_color(*BLACK)
        y = self.get_y()
        self.cell(label_w, 5.4, label)
        self._set_f("", 9.5)
        self.set_xy(MARGIN + label_w, y)
        self._mc(value)

    def _para(self, text):
        """Justified paragraph; swaps `➢`/`❖` for cp1252-safe `•`/`-`."""
        text = (text or "").replace("\u27a2", "\u2022").replace("\u2756", "-")
        self._set_f("", 9.5)
        self.set_text_color(*BLACK)
        for i, para in enumerate(text.strip().split("\n\n")):
            if i:
                self.ln(2)
            self._mc(para.strip(), align="J")
        self.ln(2)

    # -- sections (spec §3 order) ------------------------------------------

    def _letterhead(self):
        org = self.org
        if org.name_hi:
            self._center(org.name_hi, 14, "B")
        self._center(org.name_en, 16, "B")
        if org.tagline_en:
            self._center(org.tagline_en, 10)
        if org.address:
            self._center(org.address, 8.5)
        self.ln(3)
        self._rule()
        self.ln(4)

    def _date_and_number(self):
        self._set_f("", 10)
        self.set_text_color(*BLACK)
        self._mc(f"Date: {_fmt_date(self.advt.published_date)}")
        self.ln(1)
        self._mc(f"Advertisement No: {self.advt.advt_number}")
        self.ln(3)

    def _company_profile(self):
        self._section("COMPANY PROFILE")
        self._center(self.advt.title.upper(), 11, "B")
        self._para(self.advt.description or DEFAULT_COMPANY_PROFILE)
        self._set_f("", 10)
        self.set_text_color(*BLACK)
        self._mc(f"Advertisement No: {self.advt.advt_number}")
        self.ln(3)

    def _post_details(self):
        self._section("POST DETAILS")
        for idx, post in enumerate(self.advt.posts.all(), start=1):
            if idx > 1:
                self._rule()
                self.ln(3)
            self._kv("Post Code", post.post_code)
            self._kv("Name of Post", post.name)
            self._kv("No. of Vacancies", post.category_breakup_display or str(post.vacancies))
            self._kv("Qualification", post.qualification or "—")
            if post.experience_required:
                self._kv("Experience", post.experience_required)
            if post.pay_scale:
                self._kv("Remuneration", post.pay_scale)
            if post.location:
                self._kv("Location", post.location)
            if post.period_of_engagement:
                self._kv("Period of Engagement", post.period_of_engagement)
            self.ln(2)
        self.ln(1)

    def _health(self):
        self._section("HEALTH")
        self._para(self.advt.health_text or DEFAULT_HEALTH_TEXT)

    def _general_conditions(self):
        self._section("GENERAL CONDITIONS")
        self._para(self.advt.general_conditions or DEFAULT_GENERAL_CONDITIONS)

    def _how_to_apply(self):
        self._section("HOW TO APPLY")
        self._para(self.advt.how_to_apply or DEFAULT_HOW_TO_APPLY)
        if self.org.sbi_epay_text:
            self._para(self.org.sbi_epay_text)

    def _registration_schedule(self):
        self._section("REGISTRATION SCHEDULE")
        col_event, col_commence, col_close = 94, 40, 40
        header = ("Event", "Commencement Date", "Closing Date")
        rows = (
            ("Commencement of Online Registration",
             _fmt_date(self.advt.published_date), ""),
            ("Closing of Online Registration", "",
             _fmt_date(self.advt.closing_date)),
        )
        self.set_draw_color(*BLACK)
        self.set_line_width(0.4)
        self._set_f("B", 9.5)
        self.set_text_color(*BLACK)
        self.cell(col_event, 6, header[0], border=1)
        self.cell(col_commence, 6, header[1], border=1)
        self.cell(col_close, 6, header[2], border=1)
        self.ln(6)
        self._set_f("", 9.5)
        for ev, commence, close in rows:
            self.cell(col_event, 6, ev, border=1)
            self.cell(col_commence, 6, commence, border=1)
            self.cell(col_close, 6, close, border=1)
            self.ln(6)
        self.ln(2)

    def _contact(self):
        if self.org.contact_email:
            self.ln(2)
            self._set_f("", 9.5)
            self.set_text_color(*BLACK)
            self._mc(f"Contact e-mail ID of Recruitment Cell: {self.org.contact_email}")

    def footer(self):
        """Motto + Page X of Y on every page."""
        self.set_y(-15)
        self.set_font("", size=8)
        self.set_text_color(*BLACK)
        self.cell(0, 10, f"{self.org.footer_motto}  |  Page {self.page_no()} of {{nb}}", align="C")

    def generate(self):
        """Render the full advertisement and return the PDF bytes."""
        self._letterhead()
        self._date_and_number()
        self._company_profile()
        self._post_details()
        self._health()
        self._general_conditions()
        self._how_to_apply()
        self._registration_schedule()
        self._contact()
        return bytes(self.output())


def generate_advertisement_pdf(advt):
    """Return bytes of a govt-format advertisement PDF (view entry point)."""
    if FPDF is None:
        raise RuntimeError("fpdf2 not installed.")
    return AdvtPDF(advt).generate()
