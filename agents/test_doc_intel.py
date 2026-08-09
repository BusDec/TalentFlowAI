"""Tests for the document intelligence core (Phase 2, Task 1).

Covers text extraction (which must degrade gracefully to "") and the
deterministic document classifier (resume/pan/aadhaar/marksheet/
experience_letter/caste_certificate/unknown).
"""


def test_extract_text_returns_string():
    from agents import doc_intel
    assert doc_intel.extract_text("nonexistent-file.pdf") == ""


def test_classify_pan():
    from agents import doc_intel
    text = "INCOME TAX DEPARTMENT\nPermanent Account Number\nABCDE1234F\nName: RAM KUMAR\nFather's Name: SHYAM KUMAR"
    assert doc_intel.classify_document(text) == "pan"


def test_classify_aadhaar():
    from agents import doc_intel
    text = "GOVERNMENT OF INDIA\nUnique Identification Authority\n1234 5678 9012\nName: Asha Devi\nDOB: 15/06/1995"
    assert doc_intel.classify_document(text) == "aadhaar"


def test_classify_marksheet():
    from agents import doc_intel
    text = "UNIVERSITY OF MEGHALAYA\nB.TECH (CIVIL) — SEMESTER VI\nROLL NO: 2012013\nPERCENTAGE: 78.5%\nCGPA: 8.25"
    assert doc_intel.classify_document(text) == "marksheet"


def test_classify_unknown_defaults_resume():
    from agents import doc_intel
    assert doc_intel.classify_document("garbage text no markers") == "resume"


def test_extract_pan_valid():
    from agents import doc_intel
    r = doc_intel.extract_pan("ABCDE1234F\nName: RAM KUMAR")
    assert r["pan"] == "ABCDE1234F"


def test_aadhaar_verhoeff_valid_and_invalid():
    from agents import doc_intel
    # Canonical Verhoeff fixtures: an all-zero payload (00000000000) has check
    # digit 3, so 000000000003 is valid; 486199074618 is a valid Aadhaar
    # checksum example. Corrupt one digit of a valid number -> must fail.
    assert doc_intel._verhoeff_valid("000000000003") is True
    assert doc_intel._verhoeff_valid("486199074618") is True
    assert doc_intel._verhoeff_valid("486199074611") is False


def test_extract_marksheet_fields():
    from agents import doc_intel
    text = "UNIVERSITY OF MEGHALAYA\nROLL NO: 2012013\nPERCENTAGE: 78.5%\nCGPA: 8.25\nYear: 2023"
    r = doc_intel.extract_marksheet(text)
    assert r["percentage"] == "78.5%" and r["cgpa"] == "8.25" and r["year"] == "2023"


def test_extract_document_shape():
    from agents import doc_intel
    r = doc_intel.extract_document("missing.pdf")
    assert "doc_type" in r and "fields" in r and "confidence" in r and "validations" in r


def test_resume_parser_delegates_text_first():
    from agents import resume_parser, doc_intel
    assert resume_parser.extract_text.__module__ != doc_intel.__name__  # still its own function
    # smoke: parse_resume on a text/plain file keeps working
    import os, tempfile, pathlib
    fd, name = tempfile.mkstemp(suffix=".txt")
    os.close(fd)  # mkstemp leaves the handle open; release it so unlink works on Windows
    p = pathlib.Path(name)
    p.write_text("Name: Aarav Sharma\nEmail: a@b.com\nB.Tech", encoding="utf-8")
    parsed, confidence, method = resume_parser.parse_resume(str(p))
    assert isinstance(parsed, dict) and parsed.get("email") == "a@b.com"
    p.unlink()
