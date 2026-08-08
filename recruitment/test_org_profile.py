"""OrgProfile — per-tenant organisation identity tests."""


def test_org_profile_model_created(tenant):
    from recruitment.models import OrgProfile

    OrgProfile.objects.create(name_en="Test Org")
    assert OrgProfile.objects.filter(name_en="Test Org").exists()
    assert OrgProfile.objects.get(name_en="Test Org").accent_color == "#0b3d91"


def test_get_org_profile_creates_singleton(tenant):
    from recruitment.models import OrgProfile
    from recruitment.org_profile import get_org_profile

    # Defensive: drop any pre-existing row so this test exercises the
    # helper's own get_or_create defaults.
    OrgProfile.objects.all().delete()
    first = get_org_profile()
    second = get_org_profile()
    assert first.pk == second.pk
    assert first.name_en == "NEEPCO"  # fixture Client name


def test_get_org_profile_no_client_fallback(tenant, monkeypatch):
    from tenants.models import Client

    def raise_does_not_exist(*args, **kwargs):
        raise Client.DoesNotExist

    monkeypatch.setattr(Client.objects, "get", raise_does_not_exist)

    from recruitment.models import OrgProfile
    from recruitment.org_profile import get_org_profile

    OrgProfile.objects.all().delete()  # Defensive: drop any pre-existing row
    profile = get_org_profile()
    assert profile.name_en  # falls back to schema name, non-empty


def test_generate_advt_text_uses_org_profile(tenant, advertisement):
    from recruitment.org_profile import get_org_profile
    from recruitment.views import generate_advt_text

    org = get_org_profile()
    org.name_en = "ACME Energy Ltd"
    org.tagline_en = "Power For All"
    org.address = "123 Test Street"
    org.contact_email = "careers@acme.example"
    org.sbi_epay_text = "Pay Rs 500 via SBI ePay"
    org.save()
    advertisement.description = "Test company profile description."
    advertisement.save()

    text = generate_advt_text(advertisement)
    assert "ACME Energy Ltd" in text
    assert "Power For All" in text
    assert "123 Test Street" in text
    assert "careers@acme.example" in text
    assert "SBI ePay" in text
    assert "North Eastern Electric Power Corporation Limited" not in text


def test_generate_offer_text_uses_org_profile(tenant, application):
    from recruitment.org_profile import get_org_profile
    from recruitment.views import generate_offer_text

    org = get_org_profile()
    org.name_en = "ACME Energy Ltd"
    org.address = "123 Test Street"
    org.save()

    text = generate_offer_text(application)
    assert "ACME Energy Ltd" in text
    assert "123 Test Street" in text
    assert "North Eastern Electric Power Corporation Limited" not in text
