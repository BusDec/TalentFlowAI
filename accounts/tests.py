"""RBAC tests — role-based access control over internal staff views."""

from recruitment.models import PanelList


def test_anonymous_redirected_to_login(api_client):
    response = api_client.get("/")
    assert response.status_code == 302
    assert "/login/" in response["Location"]


def test_viewer_can_view_dashboard(api_client, viewer_user):
    api_client.force_login(viewer_user)
    response = api_client.get("/")
    assert response.status_code == 200


def test_viewer_blocked_from_panel_promote(api_client, viewer_user, application):
    post = application.post
    panel = PanelList.objects.create(post=post, application=application, panel_rank=1)
    api_client.force_login(viewer_user)
    response = api_client.post(f"/panel/{post.id}/promote/{panel.id}/")
    assert response.status_code == 403


def test_super_admin_bypasses_all(api_client, super_admin_user, application):
    post = application.post
    panel = PanelList.objects.create(post=post, application=application, panel_rank=1)
    api_client.force_login(super_admin_user)
    response = api_client.post(f"/panel/{post.id}/promote/{panel.id}/")
    assert response.status_code == 302
    application.refresh_from_db()
    assert application.status == "offered"


def test_recruiter_blocked_from_offer_letter_post(
    api_client, recruiter_user, org_admin_user, application
):
    api_client.force_login(recruiter_user)
    response = api_client.post(f"/applications/{application.application_id}/offer/")
    assert response.status_code == 403

    api_client.force_login(org_admin_user)
    response = api_client.post(f"/applications/{application.application_id}/offer/")
    assert response.status_code == 200


def test_viewer_blocked_from_roster_mutation(
    api_client, viewer_user, staff_user, application
):
    post = application.post
    api_client.force_login(viewer_user)
    response = api_client.post(f"/roster/{post.id}/", {"action": "generate"})
    assert response.status_code == 403

    api_client.force_login(staff_user)
    response = api_client.post(f"/roster/{post.id}/", {"action": "generate"})
    assert response.status_code == 302


def test_viewer_blocked_from_application_status_change(
    api_client, viewer_user, application
):
    api_client.force_login(viewer_user)
    response = api_client.post(
        f"/applications/{application.application_id}/",
        {"status": "shortlisted"},
    )
    assert response.status_code == 403


def test_recruiter_can_view_application_detail(api_client, recruiter_user, application):
    api_client.force_login(recruiter_user)
    response = api_client.get(f"/applications/{application.application_id}/")
    assert response.status_code == 200
