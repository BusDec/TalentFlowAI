# Document Intelligence Pipeline (Phase 2.4)

**Date**: 2026-08-08
**Status**: Approved design (Wave 1 of remaining roadmap) — awaiting implementation plan
**Source**: `docs/specs/2026-08-08-production-grade-roadmap.md` §2.4

---

## 1. Problem

`agents/resume_parser.py` today:
- Always OCRs (200 DPI) even when the PDF has a text layer — slow and unnecessary.
- One generic `SYSTEM_PROMPT`, one flat output schema, single confidence number.
- No document-type awareness (cannot distinguish PAN / Aadhaar / marksheet / experience letter / caste certificate from a resume).
- No format validation, no cross-document consistency checks.

## 2. Goal

A document-intelligence layer that: extracts text-layer-first (OCR only when needed), classifies document type, extracts per-type structured fields with **per-field confidence**, validates formats (PAN regex, Aadhaar Verhoeff checksum, percentage range), and checks cross-document name consistency. LLM-first with the existing deterministic fallback — works with no API key. Integrates with the async pipeline via a `parse_document_task`.

## 3. New module: `agents/doc_intel.py`

Pure functions, no Django model imports (except none — stays agent-layer like `resume_parser`):

- `extract_text(path) -> str` — **text-first**: if `fitz` is importable and the file is a PDF, try `page.get_text()` across pages; if the joined text is empty (scanned), fall back to OCR at **300 DPI** with `eng+hin` when Tesseract supports it (`pytesseract.get_languages()` check), else `eng`. Non-PDF (images/text) → OCR/passthrough as today. Returns "" on total failure.
- `classify_document(text) -> str` — deterministic keyword/regex rules first, LLM classification second (existing `is_configured()` / `get_llm_client()` chain), fallback `"resume"`. Classes: `resume`, `pan`, `aadhaar`, `marksheet`, `experience_letter`, `caste_certificate`, `unknown`.
- Per-type extractors (deterministic-first, LLM second — same pattern as `parse_resume`):
  - `extract_pan(text)`: PAN `[A-Z]{5}[0-9]{4}[A-Z]` (+ optional 4th-char `[ABCFGHLJPTKF]` hint), nearby name line (reuse `_clean_name` heuristics from resume_parser).
  - `extract_aadhaar(text)`: 12-digit (grouped `\d{4}\s?\d{4}\s?\d{4}` or contiguous), **Verhoeff checksum validation** (pure-Python `_verhoeff` ~25 lines), name + DOB from nearby lines.
  - `extract_marksheet(text)`: percentage (`\d{1,3}(\.\d+)?\s?%`), CGPA (`\d\.\d{2}`), university/board (line containing "UNIVERSITY"/"BOARD"/"INSTITUTE"), year (`20\d{2}`), roll number (`\b\d{6,10}\b` near "ROLL").
  - `extract_experience_letter(text)`: organisation name, employment dates (`\d{1,2}[/-]\d{4}` pairs or `20\d{2}\s*[-–]\s*(20\d{2}|till date|present)`), designation keywords (reuse resume_parser's designation list).
  - `extract_caste_certificate(text)`: category keywords SC/ST/OBC/EWS/PwBD + "CERTIFICATE" presence + district/issuing authority line.
  - `extract_resume(text)`: delegates to the existing `resume_parser._heuristic_extract` / LLM path.
- `extract_document(path) -> dict`:
  ```python
  {
      "doc_type": "pan" | ...,
      "fields": {field: value, ...},          # typed values where possible
      "confidence": {field: 0.0-1.0, ...},    # per-field confidence
      "method": "llm" | "heuristic",
      "validations": {"pan_format": True, "aadhaar_checksum": False, ...},
      "extracted_text_length": int,
  }
  ```
- `check_consistency(documents: list[dict]) -> list[dict]` — compares `name` across documents (reuse `resume_parser.names_match` / `_norm_name`-style normalization); returns `{"field": "name", "docs": ["pan","aadhaar"], "consistent": bool, "detail": str}` entries.

## 4. resume_parser integration

- `agents/resume_parser.py` `extract_text(path)` delegates to `doc_intel.extract_text` (text-first behavior applies to resumes too — OCR only when the text layer is empty). `parse_resume` signature/return unchanged (tasks/tests keep working). DPI 200 → 300 via the shared path.
- `_pdf_to_images` stays for OCR rendering; add optional preprocessing (deskew/denoise) **behind an optional OpenCV import** — if `cv2` is unavailable, skip preprocessing (no hard dependency).

## 5. Async integration

- New task in `recruitment/tasks.py`: `parse_document_task(document_id)` — fetches `Document`, sets a `parse_status`-style marker if present (Document has no status field — store result in `extracted_data`), runs `doc_intel.extract_document(document.file.path)`, writes `Document.extracted_data = {...}` and, when the classifier is confident (not `unknown`/`resume`), sets `Document.doc_type = <detected>` (doc_type is a CharField, no choices constraint — safe). Exceptions → `extracted_data = {"error": str(e)[:500]}` (never re-raise).
- Wire: in `portal/views.py` apply flow, after each certificate `Document.objects.create(...)`, call `parse_document_task.delay(document.id)` (eager in dev, Celery in prod — existing pattern).

## 6. Error handling

- `extract_text` returns "" (never raises) → classifier returns `"unknown"` → `extract_document` returns `{"doc_type": "unknown", "fields": {}, ...}`.
- Missing optional deps (fitz, pytesseract, cv2) degrade per step (text-layer try → OCR skip → ""); no hard imports.
- Verhoeff/PAN validators never raise on malformed input (False result).
- LLM failures → deterministic fallback (existing pattern), never a crash.

## 7. Testing (`agents/test_doc_intel.py` + `recruitment/test_tasks.py`)

| Test | Asserts |
|---|---|
| classify pan/aadhaar/marksheet/experience/caste | keyword rules on synthetic texts |
| extract_pan | valid PAN matched; 4th-char hint; invalid rejected |
| extract_aadhaar + verhoeff | valid 12-digit passes checksum; invalid fails; grouped format |
| extract_marksheet | % and CGPA and university/year extracted |
| extract_experience | org + date range + designation |
| extract_caste | category keyword + certificate present |
| text-first extraction | text-PDF (fixture with `fitz`-generated or simple text) returns text without OCR — use a tiny valid PDF generated in-test via fitz if available, else skipif |
| consistency | same name across two docs → consistent; mismatch → inconsistent entry |
| parse_document_task | task populates extracted_data; error case writes {"error": ...} |

## 8. Commands after implementation

1. `pytest -q` full suite
2. Live E2E (portal apply with a certificate upload populates `Document.extracted_data`; resume parse still green)

## 9. Commit format

`Phase 2: DocIntel — <brief>`
