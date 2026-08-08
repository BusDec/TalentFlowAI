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
