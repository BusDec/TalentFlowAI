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
