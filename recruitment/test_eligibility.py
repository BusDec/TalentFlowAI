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
