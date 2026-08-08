"""Template context processors for the candidate portal."""


def org_profile(request):
    from recruitment.org_profile import get_org_profile

    return {"org_profile": get_org_profile()}
