"""Resume Parsing Agent.

Extracts structured fields from a candidate resume PDF/image using Tesseract OCR
(local, free) followed by LLM structuring. Gracefully degrades to OCR-only when
no LLM API key is configured, and can fall back to keyword heuristics so the
agent works in demo mode without any external calls.
"""

import os
import re
import datetime

from django.conf import settings

from agents.llm_client import get_llm_client, is_configured, LLMClientError

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:  # pragma: no cover
    OCR_AVAILABLE = False

# Point pytesseract at the Tesseract binary when it's not on PATH (Windows).
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


SYSTEM_PROMPT = (
    "You extract structured information from an Indian job candidate's resume. "
    "Return ONLY a JSON object with keys: full_name, email, phone, date_of_birth, "
    "degree, university, year_of_passing, percentage, total_experience_years, "
    "skills (list), current_designation, current_organization. "
    "Use null for missing values. No commentary."
)


def extract_text(path):
    """Extract plain text from a resume PDF/image/text file (text-first).

    Delegates to doc_intel, which pulls the PDF text layer first and only
    OCRs when it is empty. Kept as its own function so callers and tests
    keep a stable module-level entry point.
    """
    from . import doc_intel

    return doc_intel.extract_text(path)


_NAME_LABEL = re.compile(
    r"(?im)^\s*(?:name|candidate name|candidate|full name|applicant name|applicant)\s*[:\-]\s*([a-z][a-z'.\-\s]{2,60})"
)
_NAME_NOISE = {"mr", "mrs", "ms", "dr", "shri", "smt", "kumari", "er", "prof"}
_NAME_BLOCKING = [
    "email", "phone", "mobile", "address", "linkedin", "github", "resume",
    "curriculum", "vitae", "cv", "street", "road", "nagar", "colony", "india",
    "city", "career", "objective", "profile", "summary", "contact", "http",
]


def _clean_name(name):
    """Strip honorifics and tidy whitespace/punctuation from a name."""
    name = re.sub(r"\b(?:mr|mrs|ms|dr|shri|smt|kumari|er|prof)\.?\b", " ", name, flags=re.I)
    name = re.sub(r"\s+", " ", name)
    return name.strip(" .,-")


def _looks_like_name(line):
    """Heuristic: is this line a plausible person name?"""
    line = line.strip()
    if not line or len(line) < 3 or len(line) > 60:
        return False
    if not re.match(r"^[A-Za-z][A-Za-z.'\-\s]*$", line):
        return False
    words = [w for w in line.split() if w]
    if len(words) < 2:
        return False
    # Most words should be capitalised, typical of a proper name.
    caps = sum(1 for w in words if w[0].isupper())
    if caps < max(2, len(words) - 1):
        return False
    low = line.lower()
    return not any(b in low for b in _NAME_BLOCKING)


def _extract_name(text):
    """Best-effort person name extraction from resume text."""
    label = _NAME_LABEL.search(text)
    if label:
        cleaned = _clean_name(label.group(1))
        if cleaned and not any(b in cleaned.lower() for b in _NAME_BLOCKING):
            return cleaned
        # The label group's character class includes \s, so it can swallow the
        # following line ("Name: Aarav Sharma\nEmail: …" → "Aarav Sharma Email: …"),
        # which then trips the blocklist. Preserve the matched line itself and
        # give it the clean-name path.
        first_line = label.group(1).splitlines()[0]
        cleaned = _clean_name(first_line)
        if cleaned and not any(b in cleaned.lower() for b in _NAME_BLOCKING):
            return cleaned
    for line in text.splitlines()[:10]:
        line = line.strip()
        if not line:
            continue
        if re.search(r"[\w.\-+]+@[\w\-]+\.[\w.\-]+", line, re.I):
            continue
        if _looks_like_name(line):
            return _clean_name(line)
    return None


def names_match(parsed_name, applicant_name):
    """Compare an extracted resume name with the applicant's registered name.

    Returns True if they match, False if they clearly differ, None when they
    cannot be compared (either name missing). Requires agreement on both the
    given name and the family name, so a shared surname alone is a mismatch.
    """
    if not parsed_name or not applicant_name:
        return None
    p = [t for t in re.findall(r"[a-z]+", _clean_name(parsed_name).lower()) if t not in _NAME_NOISE]
    a = [t for t in re.findall(r"[a-z]+", _clean_name(applicant_name).lower()) if t not in _NAME_NOISE]
    if not p or not a:
        return None

    same_first = p[0] == a[0]
    same_last = p[-1] == a[-1]
    common = set(p) & set(a)

    if same_first and same_last:
        return True
    # A single-token name matches if it appears in the other name.
    if len(p) == 1 and p[0] in a:
        return True
    if len(a) == 1 and a[0] in p:
        return True
    # Same given name plus a near-full token overlap (e.g. extra middle name).
    if same_first and len(common) >= max(1, min(len(p), len(a)) - 1):
        return True
    return False


def _extract_dob(text):
    """Best-effort date-of-birth extraction from resume text."""
    m = re.search(
        r"(?i)\b(?:date\s*of\s*birth|dob|d\.o\.b\.?|birth\s*date|born)\b\s*[:\-]?\s*"
        r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        text,
    )
    if not m:
        return None
    raw = m.group(1)
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y", "%d.%m.%y"):
        try:
            return datetime.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _heuristic_extract(text):
    """Deterministic fallback so the agent works without an LLM key."""
    email = re.search(r"[\w.\-+]+@[\w\-]+\.[\w.\-]+", text)
    phone = re.search(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)", text)
    years = re.findall(r"\b((?:19|20)\d{2})\b", text)
    lower = text.lower()

    # Estimate total experience from date-range job rows like "2019 - Present".
    exp_years = None
    ranges = re.findall(r"\b((?:19|20)\d{2})\s*[-–]\s*((?:19|20)\d{2}|present|now|current)\b", text, re.I)
    if ranges:
        # Sum span of each employment range.
        total_months = 0
        for a, b in ranges:
            try:
                start = int(a)
                end = int(b) if b.isdigit() else datetime.date.today().year
                if end >= start:
                    total_months += (end - start) * 12
            except ValueError:
                continue
        exp_years = round(total_months / 12) if total_months else None

    # Skills — pick known power/construction keywords present in the text.
    known_skills = [
        "SAP", "AutoCAD", "Primavera", "MS Project", "FIDIC", "SCADA", "Survey",
        "Financial Modelling", "Emergency Medicine", "Occupational Health", "Critical Care",
        "Substation", "Power Systems", "Hydro", "Power", "Construction", "Contract",
        "Budgeting", "Audit", "Taxation", "GST", "Excel", "Drafting", "S/4HANA",
    ]
    skills = [s for s in known_skills if s.lower() in lower]

    # Degree guess
    degree = None
    if any(t in lower for t in ["b.tech", "b.e", "btech"]):
        degree = "B.Tech Engineering"
    elif "mbbs" in lower:
        degree = "MBBS"
    elif "mba" in lower:
        degree = "MBA"
    elif "diploma" in lower:
        degree = "Diploma"
    elif "ca" in lower or "chartered accountant" in lower:
        degree = "CA"

    # Designation / organisation
    designation = None
    org = None
    desig_match = re.search(r"(Assistant Manager|Manager|Engineer|Medical Officer|Supervisor|Analyst|Associate)\b[^|\n]*", text, re.I)
    if desig_match:
        designation = desig_match.group(0).strip()
    org_match = re.search(r"\|\s*([A-Z][A-Za-z0-9 &.-]{3,})", text)
    if org_match and "phone" not in org_match.group(1).lower():
        org = org_match.group(1).strip()

    return {
        "full_name": _extract_name(text),
        "email": email.group(0) if email else None,
        "phone": phone.group(0) if phone else None,
        "date_of_birth": _extract_dob(text),
        "degree": degree,
        "university": None,
        "year_of_passing": None,
        "percentage": None,
        "total_experience_years": exp_years,
        "skills": skills,
        "current_designation": designation,
        "current_organization": org,
    }


def _extract_json_from_llm(raw):
    """Best-effort JSON parse of LLM output (strip fences/extra text)."""
    import json

    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def parse_resume(path):
    """Return (parsed_dict, confidence, method) for a resume file path.

    method is one of: 'llm', 'heuristic'.
    """
    text = extract_text(path)
    if not text:
        return {"error": "OCR failed"}, 0.0, "ocr_failed"

    parsed = None
    method = "heuristic"
    if is_configured():
        try:
            client = get_llm_client()
            raw = client.complete(SYSTEM_PROMPT, f"Resume text:\n{text[:8000]}")
            parsed = _extract_json_from_llm(raw)
            if parsed:
                method = "llm"
        except LLMClientError:
            parsed = None

    if parsed is None:
        parsed = _heuristic_extract(text)

    confidence = 0.9 if method == "llm" else 0.6
    parsed["_method"] = method
    parsed["_ocr_length"] = len(text)
    return parsed, confidence, method
