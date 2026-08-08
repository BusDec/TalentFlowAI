"""OrgProfile — per-tenant organisation identity tests."""


def test_org_profile_model_created(tenant):
    from recruitment.models import OrgProfile

    OrgProfile.objects.create(name_en="Test Org")
    assert OrgProfile.objects.filter(name_en="Test Org").exists()
    assert OrgProfile.objects.get(name_en="Test Org").accent_color == "#0b3d91"
