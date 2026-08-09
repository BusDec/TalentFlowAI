"""Document Intelligence core (Phase 2, Task 1).

Produces the two primitives every downstream document agent consumes:

* ``extract_text(path)`` — pull plain text out of a document file. PDFs use
  the PyMuPDF text layer first (fast, lossless); when that is empty or fitz
  is unavailable, pages are rendered and OCR'd with local Tesseract at
  300 DPI. Non-PDF files are raw-read when they are text, OCR'd when they
  are images, and best-effort otherwise. Every failure path degrades to "".
* ``classify_document(text)`` — deterministically classify raw document text
  into one of the known document classes (resume/pan/aadhaar/marksheet/
  experience_letter/caste_certificate/unknown), with a best-effort LLM
  fallback when one is configured and a "resume" default otherwise.
* Per-type extractors (``extract_pan``/``extract_aadhaar``/``extract_marksheet``/
  ``extract_experience_letter``/``extract_caste_certificate``/``extract_resume``)
  pull structured fields out of classified text, with ``_verhoeff_valid``
  backing Aadhaar checksum validation.
* ``extract_document(path)`` — orchestration: text -> classify -> per-type
  extraction, returning per-field confidence and per-type validations.

Consumed by Tasks 3-5 (validation and PII handling).
"""

import os
import re

from agents.llm_client import get_llm_client, is_configured

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:  # pragma: no cover
    OCR_AVAILABLE = False

# Point pytesseract at the Tesseract binary when it's not on PATH (Windows).
# Same discovery loop as agents/resume_parser.py.
for _candidate in (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
):
    if os.path.exists(_candidate):
        pytesseract.pytesseract.tesseract_cmd = _candidate
        break

for _tessdata in (
    r"C:\Program Files\Tesseract-OCR\tessdata",
    os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tessdata"),
):
    if os.path.isdir(_tessdata):
        os.environ.setdefault("TESSDATA_PREFIX", _tessdata)
        break

# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

_TEXT_EXTS = {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".html", ".htm",
              ".xml", ".ini", ".cfg", ".rtf"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif"}


def extract_text(path):
    """Extract plain text from a PDF, image or text file.

    Returns "" for unreadable, empty, or OCR-failure documents so callers can
    always rely on a string result.
    """
    try:
        if not path:
            return ""
        name = str(path)
        if name.lower().endswith(".pdf"):
            return _extract_pdf(name)
        return _extract_other(name)
    except Exception:
        return ""


def _extract_pdf(path):
    """PDF text layer first (PyMuPDF); fall back to OCR at 300 DPI."""
    text = ""
    try:
        import fitz  # PyMuPDF
        with fitz.open(path) as doc:
            text = "\n".join(page.get_text("text") for page in doc)
    except ImportError:  # fitz absent -> treat as no text layer
        text = ""
    if text and text.strip():
        return text
    if not OCR_AVAILABLE:
        return ""
    try:
        import fitz  # PyMuPDF
        images = []
        with fitz.open(path) as doc:
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                images.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        return "\n".join(
            pytesseract.image_to_string(img, lang=_ocr_lang()) for img in images
        )
    except Exception:
        return ""


def _extract_other(path):
    """Raw-read text files, OCR image files, best-effort for anything else."""
    ext = os.path.splitext(path)[1].lower()
    if ext in _IMAGE_EXTS:
        if not OCR_AVAILABLE:
            return ""
        try:
            return pytesseract.image_to_string(Image.open(path), lang=_ocr_lang())
        except Exception:
            return ""
    if ext in _TEXT_EXTS:
        return _read_raw(path)
    # Unknown type: prefer raw text when it decodes; otherwise try OCR.
    raw = _read_raw(path)
    if raw and "\x00" not in raw[:4096]:
        return raw
    if OCR_AVAILABLE:
        try:
            return pytesseract.image_to_string(Image.open(path), lang=_ocr_lang())
        except Exception:
            pass
    return raw


def _read_raw(path):
    """Read a file as text across common encodings; "" on any failure."""
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, OSError):
            continue
    return ""


def _ocr_lang():
    """Tesseract language string: 'eng+hin' when Hindi training data exists."""
    try:
        langs = pytesseract.get_languages()
        if any(str(lang).strip().lower() == "hin" for lang in langs):
            return "eng+hin"
    except Exception:
        pass
    return "eng"


# ---------------------------------------------------------------------------
# Document classification
# ---------------------------------------------------------------------------

CLASSES = ("resume", "pan", "aadhaar", "marksheet", "experience_letter",
           "caste_certificate", "unknown")

_PAN_RE = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")
_AADHAAR_RE = re.compile(r"\d{4}\s*\d{4}\s*\d{4}")
_MARKSHEET_KW = ("university", "board", "institute")
_MARKSHEET_FIELD = ("percentage", "cgpa", "roll")
_EXP_KW = ("experience certificate", "experience letter", "employment")
_DATE_RANGE_RE = re.compile(
    r"(?i)\b(?:"
    r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"                                 # 15/06/1995
    r"|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\.?\s+(?:\d{1,2}(?:st|nd|rd|th)?\s*,?\s+)?\d{4}"     # 15 June 1995 / June 1995
    r"|\d{4}\s*(?:-|\u2013|\u2014|to)\s*\d{4}"                           # 2019-2023
    r"|since\s+\d{4}"
    r")"
)
_CAST_KW = ("caste", "category certificate", "obc", "ews", "pwbd")
_CAST_SHORT_RE = re.compile(r"\b(?:sc|st)\b", re.IGNORECASE)


def classify_document(text):
    """Classify raw document text into one of the known document classes.

    Deterministic keyword/regex rules run in a fixed order (pan, aadhaar,
    marksheet, experience_letter, caste_certificate). Documents that match
    nothing fall through to a best-effort LLM classification when one is
    configured, and otherwise default to "resume".
    """
    if not text:
        return "resume"
    low = text.lower()

    if _PAN_RE.search(text) and (
        "permanent account number" in low or "income tax" in low
    ):
        return "pan"

    if _AADHAAR_RE.search(text) and any(
        k in low for k in ("uidai", "aadhaar", "unique identification")
    ):
        return "aadhaar"

    if any(k in low for k in _MARKSHEET_KW) and any(
        k in low for k in _MARKSHEET_FIELD
    ):
        return "marksheet"

    if any(k in low for k in _EXP_KW) and _DATE_RANGE_RE.search(text):
        return "experience_letter"

    if "certificate" in low and (
        any(k in low for k in _CAST_KW) or _CAST_SHORT_RE.search(text)
    ):
        return "caste_certificate"

    label = _llm_classify(text)
    if label and label != "unknown":
        return label
    return "resume"


_LLM_SYSTEM_PROMPT = (
    "You classify an extracted document snippet from an Indian recruitment "
    "process. Reply with exactly one lowercase token chosen from: resume, pan, "
    "aadhaar, marksheet, experience_letter, caste_certificate, unknown. "
    "No commentary."
)


def _llm_classify(text):
    """Best-effort LLM classification; returns a class label or None.

    Only invoked when an LLM is configured, and never for trivial inputs —
    the deterministic "resume" default is correct for those and an LLM call
    would be wasted. Any failure (auth, network, timeout, malformed reply)
    degrades to None so callers keep the deterministic default.
    """
    if not is_configured():
        return None
    if len(text.strip()) < 40:
        return None
    try:
        client = get_llm_client()
        raw = client.complete(
            _LLM_SYSTEM_PROMPT,
            f"Document text:\n{text[:4000]}",
            max_tokens=8,
            temperature=0,
        )
    except Exception:
        return None
    if not raw:
        return None
    label = raw.strip().strip(".,;:'\"`").lower()
    return label if label in CLASSES else None


# ---------------------------------------------------------------------------
# Verhoeff checksum (Aadhaar)
# ---------------------------------------------------------------------------

_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6), (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8), (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2), (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4), (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2), (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0), (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5), (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def _verhoeff_valid(number):
    """Standard Verhoeff checksum validation (pure Python, dihedral tables).

    Returns True for a valid number and False for anything else (malformed,
    non-digit, or checksum mismatch). Never raises.
    """
    digits = str(number)
    if not digits.isdigit():
        return False
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


# ---------------------------------------------------------------------------
# Per-type extractors
# ---------------------------------------------------------------------------

_NAME_BLOCKED = ("father", "mother", "spouse", "husband", "wife", "guardian",
                 "parent")
_NAME_LABEL_RE = re.compile(
    r"(?i)^\s*(?:"
    r"(?:applicant|candidate|father|mother|spouse|husband|wife|guardian)'?s?\s+name"
    r"|name\s+of\s+(?:the\s+)?(?:applicant|candidate)"
    r"|full\s+name"
    r"|name"
    r")\s*[:.\-]?\s*(.+?)\s*$"
)
_DOB_RE = re.compile(
    r"(?i)\b(?:date\s*of\s*birth|dob|d\.o\.b\.?|birth\s*date)\s*[:.\-]?\s*"
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})"
)
_PAN_FULL_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_AADHAAR_FULL_RE = re.compile(r"\d{4}\s*\d{4}\s*\d{4}")
_PCT_RE = re.compile(r"\d{1,3}(?:\.\d+)?\s?%")
_CGPA_RE = re.compile(r"\b\d\.\d{2}\b")
_CGPA_LOOSE_RE = re.compile(r"\b\d\.\d\b")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_UNIVERSITY_KW = ("university", "board", "institute")
_ROLL_RE = re.compile(r"(?i)\broll\s*(?:no\.?|number)?\s*[:.\-]?\s*(\d{6,10})\b")
_ORG_RE = re.compile(r"(?i)^\s*(?:organization|organisation|company)\s*:?\s*(.+?)\s*$")
_EXP_YEAR_RANGE_RE = re.compile(
    r"(?i)\b((?:19|20)\d{2})\s*(?:-|–|—|to)\s*((?:19|20)\d{2}|till\s*date|present)\b"
)
_EXP_DAY_RANGE_RE = re.compile(
    r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\s*(?:-|–|—|to)\s*"
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b"
)
_DESIGNATION_LABEL_RE = re.compile(
    r"(?i)^\s*(?:designation|position|post|role)\s*:?\s*(.+?)\s*$"
)
_DESIGNATION_KW_RE = re.compile(
    r"(?i)\b(?:assistant\s+manager|manager|engineer|medical\s+officer|"
    r"supervisor|analyst|associate)\b"
)
_CAST_CATEGORY_RE = re.compile(r"\b(?:sc|st|obc|ews|pwbd|pwd)\b", re.IGNORECASE)
_AUTHORITY_RE = re.compile(
    r"(?i)^\s*(?:issuing\s*authority|issued\s*by|office|district)\s*:?\s*(.+?)\s*$"
)
_AUTHORITY_KW = ("district", "office", "tehsildar", "sub-divisional", "collector")


def _extract_name(text):
    """Best-effort labelled name extraction (ignores relative-name lines)."""
    for line in text.splitlines():
        if any(b in line.lower() for b in _NAME_BLOCKED):
            continue
        m = _NAME_LABEL_RE.match(line)
        if m:
            name = m.group(1).strip().strip(".,- ")
            if name and len(name) >= 2:
                return name
    return None


def _extract_dob(text):
    """Raw date-of-birth string (DD/MM/YYYY family) or None."""
    m = _DOB_RE.search(text)
    return m.group(1) if m else None


def extract_pan(text):
    """Extract PAN and a nearby name from PAN-card text."""
    m = _PAN_FULL_RE.search(text)
    return {"pan": m.group(0) if m else None, "name": _extract_name(text)}


def extract_aadhaar(text):
    """Extract Aadhaar number (Verhoeff-validated), name and DOB."""
    m = _AADHAAR_FULL_RE.search(text)
    digits = re.sub(r"\s+", "", m.group(0)) if m else None
    return {
        "aadhaar": digits,
        "name": _extract_name(text),
        "dob": _extract_dob(text),
        "valid": bool(digits and _verhoeff_valid(digits)),
    }


def extract_marksheet(text):
    """Extract percentage, CGPA, university, year and roll number."""
    pct = _PCT_RE.search(text)
    cgpa = _CGPA_RE.search(text) or _CGPA_LOOSE_RE.search(text)
    univ = None
    for line in text.splitlines():
        if any(k in line.lower() for k in _UNIVERSITY_KW):
            univ = line.strip()
            break
    year = _YEAR_RE.search(text)
    roll = _ROLL_RE.search(text)
    return {
        "percentage": pct.group(0).strip() if pct else None,
        "cgpa": cgpa.group(0) if cgpa else None,
        "university": univ,
        "year": year.group(1) if year else None,
        "roll_no": roll.group(1) if roll else None,
    }


def extract_experience_letter(text):
    """Extract organisation, employment period and designation."""
    org = None
    for line in text.splitlines():
        m = _ORG_RE.match(line)
        if m:
            org = m.group(1).strip()
            break
    start = end = None
    m = _EXP_YEAR_RANGE_RE.search(text)
    if m:
        start, end = m.group(1), m.group(2)
    else:
        m = _EXP_DAY_RANGE_RE.search(text)
        if m:
            start, end = m.group(1), m.group(2)
    designation = None
    dm = _DESIGNATION_LABEL_RE.search(text)
    if dm:
        designation = dm.group(1).strip()
    else:
        km = _DESIGNATION_KW_RE.search(text)
        if km:
            designation = km.group(0).title()
    return {
        "organisation": org,
        "start_date": start,
        "end_date": end,
        "designation": designation,
    }


def extract_caste_certificate(text):
    """Extract category and issuing authority from a caste certificate."""
    cm = _CAST_CATEGORY_RE.search(text)
    category = cm.group(0).upper() if cm else None
    authority = None
    for line in text.splitlines():
        m = _AUTHORITY_RE.match(line)
        if m:
            authority = m.group(1).strip()
            break
    if authority is None:
        for line in text.splitlines():
            low = line.lower()
            if any(k in low for k in _AUTHORITY_KW) and len(line.strip()) > 5:
                authority = line.strip()
                break
    return {"category": category, "issuing_authority": authority}


def extract_resume(text):
    """Delegate to the existing resume heuristic extractor."""
    from agents.resume_parser import _heuristic_extract

    fields = _heuristic_extract(text)
    fields["_method"] = "heuristic"
    return fields


# ---------------------------------------------------------------------------
# Orchestration: extract_document
# ---------------------------------------------------------------------------

_EXTRACTORS = {
    "pan": extract_pan,
    "aadhaar": extract_aadhaar,
    "marksheet": extract_marksheet,
    "experience_letter": extract_experience_letter,
    "caste_certificate": extract_caste_certificate,
    "resume": extract_resume,
    "unknown": lambda text: {},
}


def _validations_for(doc_type, fields):
    """Per-type validation flags (format / checksum / range)."""
    if doc_type == "pan":
        return {"pan_format": bool(fields.get("pan"))}
    if doc_type == "aadhaar":
        return {
            "aadhaar_checksum": bool(
                fields.get("aadhaar") and fields.get("valid")
            )
        }
    if doc_type == "marksheet":
        pct = fields.get("percentage")
        value = re.sub(r"[^\d.]", "", pct) if pct else ""
        try:
            in_range = 0 <= float(value) <= 100
        except ValueError:
            in_range = False
        return {"percentage_range": bool(pct) and in_range}
    if doc_type == "experience_letter":
        return {
            "date_range": bool(
                fields.get("start_date") and fields.get("end_date")
            )
        }
    if doc_type == "caste_certificate":
        return {"category_present": bool(fields.get("category"))}
    return {}


def _validated_field(doc_type, key, validations):
    """True when a field's value is backed by a checksum/regex validation."""
    if doc_type == "pan" and key == "pan":
        return bool(validations.get("pan_format"))
    if doc_type == "aadhaar" and key == "aadhaar":
        return bool(validations.get("aadhaar_checksum"))
    if doc_type == "marksheet" and key == "percentage":
        return bool(validations.get("percentage_range"))
    return False


def _confidence_for(doc_type, fields, validations):
    """Per-field confidence: 0.95 validated, 0.7 heuristic, 0.0 for None."""
    conf = {}
    for key, value in fields.items():
        if key.startswith("_") or key == "valid":
            continue
        if value is None:
            conf[key] = 0.0
        elif _validated_field(doc_type, key, validations):
            conf[key] = 0.95
        else:
            conf[key] = 0.7
    return conf


def extract_document(path):
    """Full extraction pipeline: text -> classify -> per-type extractor.

    Returns a dict with doc_type, fields, per-field confidence, method,
    validations and extracted_text_length. Unreadable documents degrade to
    the "unknown" shape so callers can always rely on the same keys.
    """
    text = extract_text(path)
    if not text or not text.strip():
        return {
            "doc_type": "unknown",
            "fields": {},
            "confidence": {},
            "method": "heuristic",
            "validations": {},
            "extracted_text_length": 0,
        }
    doc_type = classify_document(text)
    fields = _EXTRACTORS[doc_type](text)
    validations = _validations_for(doc_type, fields)
    return {
        "doc_type": doc_type,
        "fields": fields,
        "confidence": _confidence_for(doc_type, fields, validations),
        "method": "heuristic",
        "validations": validations,
        "extracted_text_length": len(text),
    }
