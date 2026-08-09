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

Consumed by Tasks 2-5 (per-type extractors, extraction orchestration,
validation and PII handling).
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
