def test_post_has_structured_criteria(tenant, advertisement):
    from recruitment.models import Post
    post = advertisement.posts.first()
    assert hasattr(post, "min_education_level")
    assert hasattr(post, "min_percentage")
    assert hasattr(post, "experience_years")
    assert hasattr(post, "age_cutoff_date")


def test_eligibility_override_model(tenant, application):
    from accounts.models import User
    from recruitment.models import EligibilityOverride
    user = User.objects.create_user(username="ovr", password="x")
    o = EligibilityOverride.objects.create(application=application, verdict=True, reason="doc verified", overridden_by=user)
    assert o.reason == "doc verified"
    assert application.eligibility_override.pk == o.pk


def test_engine_verdict_tiers(tenant, application):
    from agents.eligibility_verifier import verify_application
    v = verify_application(application)
    assert v["verdict"] in ("eligible", "not_eligible", "manual_review")
    assert set(v) >= {"application_id", "post", "flags", "eligible", "verdict"}
    for f in ("age", "education", "experience", "certificates"):
        assert f in v["flags"] and "ok" in v["flags"][f] and "detail" in v["flags"][f]


def test_age_uses_cutoff_arg(tenant, application):
    from agents.eligibility_verifier import verify_application
    application.candidate.date_of_birth = "1995-06-15"
    application.candidate.save()
    v = verify_application(application, cutoff="2026-01-01")
    assert v["cutoff"] == "2026-01-01" or str(v["cutoff"]).startswith("2026-01-01")


def test_missing_required_certificate_false(tenant, application):
    from agents.eligibility_verifier import verify_application
    application.post.required_certificates = ["GATE scorecard"]
    application.post.save()
    v = verify_application(application)
    assert v["flags"]["certificates"]["ok"] is False
    assert "GATE scorecard" in v["flags"]["certificates"]["detail"]


def test_override_requires_reason(api_client, tenant, application, recruiter_user):
    api_client.force_login(recruiter_user)
    r = api_client.post(
        f"/applications/{application.application_id}/eligibility/",
        {"override_verdict": "on", "override_reason": ""},
    )
    assert r.status_code == 200  # re-render with error, not 302
    from recruitment.models import EligibilityOverride
    assert not EligibilityOverride.objects.filter(application=application).exists()


def test_override_writes_audit(api_client, tenant, application, recruiter_user):
    api_client.force_login(recruiter_user)
    r = api_client.post(
        f"/applications/{application.application_id}/eligibility/",
        {"override_verdict": "on", "override_reason": "documents verified"},
    )
    assert r.status_code == 302
    from recruitment.models import AuditEvent, EligibilityOverride
    o = EligibilityOverride.objects.get(application=application)
    assert o.verdict is True and o.overridden_by == recruiter_user
    assert AuditEvent.objects.filter(application=application, field_name="eligibility_override").exists()


def test_eligibility_page_renders_verdict_card(api_client, tenant, application, recruiter_user):
    api_client.force_login(recruiter_user)
    r = api_client.get(f"/applications/{application.application_id}/eligibility/")
    assert r.status_code == 200
    body = r.content.decode()
    assert "verdict" in body.lower() or "eligible" in body.lower()
