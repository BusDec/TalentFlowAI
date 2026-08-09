# Govt-Format Advertisement PDF (Phase 2.2)

**Date**: 2026-08-08 · **Status**: Approved design (Wave 2) · **Source**: roadmap §2.2

## 1. Problem
`recruitment/advt_pdf.py` renders a startup-style PDF (indigo palette, boxed sections). Govt recruitment ads need a plain formal layout. The `➢` bullet glyph is missing from fpdf's core Arial (cp1252) — the log shows `Font MPDFAA+Arial is missing the following glyphs: '➢'`.

## 2. Goal
Rewrite `AdvtPDF` to a plain A4 govt format driven by OrgProfile + Advertisement data, matching the sample document's structure.

## 3. Layout (in order)
1. **Letterhead** (centered): `name_hi` (when set) over `name_en`, `tagline_en`, `address` — from OrgProfile.
2. **Date line**: `Date: <published_date>` on its own line, then `Advertisement No: <advt_number>`.
3. **COMPANY PROFILE** section: `advt.description or DEFAULT_COMPANY_PROFILE`; advt number printed again after the header per sample.
4. **POST DETAILS**: for each post — label:value rows (Post Code, Name of Post, No. of Vacancies from category_breakup, Qualification, Experience, Remuneration, Location, Period of Engagement).
5. **HEALTH**, **GENERAL CONDITIONS**, **HOW TO APPLY** sections from `advt.health_text/general_conditions/how_to_apply`; **fee text printed inside HOW TO APPLY** (`org.sbi_epay_text`), not as a separate section.
6. **REGISTRATION SCHEDULE**: table with columns Event | Commencement Date | Closing Date (published_date / closing_date).
7. **Footer**: `org.footer_motto` + `Page X of Y` on every page (fpdf footer override).

## 4. Bullet glyphs — documented deviation
`➢` (U+27A2) and `❖` are not in fpdf core-font cp1252. Bundling a Unicode TTF is out of scope (asset pipeline). Use cp1252-safe `•` for list items and `-` for sub-items. This kills the missing-glyph warning. (Roadmap's exact glyphs noted for a future font-bundling task.)

## 5. Data sources
- OrgProfile via `get_org_profile()` (name_en/name_hi/tagline_en/address/footer_motto/sbi_epay_text).
- `Advertisement` + `Post` fields; `DEFAULT_COMPANY_PROFILE` fallback for description.
- Keep the existing `generate()` entry (`recruitment/views.py advertisement_pdf` unchanged — same view, new output).

## 6. Style
Plain black text, thin rules, no color bars/boxes; single column; A4 portrait; margins ~18mm.

## 7. Testing (`recruitment/test_advt_pdf.py`)
- `test_pdf_generates`: `AdvtPDF(advt).generate()` returns non-empty bytes starting `%PDF`.
- `test_pdf_contains_org_and_advt_data`: extract text via `doc_intel.extract_text` from a temp file; assert `name_en`, `advt_number`, a post's post_code, and `sbi_epay_text` fragment appear; assert no `➢` glyph remains (byte check for the missing-glyph char).
- `test_pdf_pages_numbered`: text contains "Page 1 of" (footer present).

## 8. Commands
`pytest -q` · E2E (advertisement_pdf route stays 200) · commit `Phase 2: AdvtPDF — govt-format layout`
