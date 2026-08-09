"""Offer letter PDF tests (Phase 2, Task 1)."""


def test_offer_pdf_contains_data(tenant, application):
    from recruitment.offer_pdf import OfferPDF
    from agents import doc_intel
    import tempfile, pathlib, os
    from recruitment.org_profile import get_org_profile

    org = get_org_profile()
    org.name_en = "ACME Energy Ltd"
    org.save()
    application.status = "offered"
    application.save()
    fd, name = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)  # release the handle so unlink works on Windows
    p = pathlib.Path(name)
    p.write_bytes(OfferPDF(application).generate())
    text = doc_intel.extract_text(str(p))
    assert "ACME Energy Ltd" in text
    assert application.application_id in text
    assert application.post.name in text
    assert "Authorised Signatory" in text
    p.unlink()


def test_offer_letter_view_streams_pdf(api_client, tenant, application, recruiter_user):
    api_client.force_login(recruiter_user)
    r = api_client.get(f"/applications/{application.application_id}/offer/")
    assert r.status_code == 200
    assert r["Content-Type"].startswith("application/pdf")
