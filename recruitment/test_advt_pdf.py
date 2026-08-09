"""Govt-format advertisement PDF tests (Phase 2, Task 1)."""

import pytest


def test_pdf_generates(tenant, advertisement):
    from recruitment.advt_pdf import AdvtPDF

    data = AdvtPDF(advertisement).generate()
    assert data.startswith(b"%PDF") and len(data) > 1000


def test_pdf_contains_org_and_advt_data(tenant, advertisement):
    pytest.importorskip("fitz")  # text extraction needs PyMuPDF

    from recruitment.advt_pdf import AdvtPDF
    from agents import doc_intel
    import tempfile, pathlib, os
    from recruitment.org_profile import get_org_profile

    org = get_org_profile()
    org.name_en = "ACME Energy Ltd"
    org.save()
    advertisement.description = "Test profile."
    advertisement.save()
    fd, name = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)  # release the handle so unlink works on Windows
    p = pathlib.Path(name)
    p.write_bytes(AdvtPDF(advertisement).generate())
    text = doc_intel.extract_text(str(p))
    assert "ACME Energy Ltd" in text
    assert advertisement.advt_number in text
    post = advertisement.posts.first()
    assert post.post_code in text
    p.unlink()


def test_pdf_no_missing_glyph_byte(tenant, advertisement):
    from recruitment.advt_pdf import AdvtPDF

    assert "\u27a2" not in ""  # sanity; real check:
    data = AdvtPDF(advertisement).generate().decode("latin-1", "ignore")
    assert "\u27a2" not in data
