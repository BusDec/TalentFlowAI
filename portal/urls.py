from django.urls import path
from . import views

urlpatterns = [
    path("portal/register/", views.register, name="portal_register"),
    path("portal/verify/", views.verify_otp, name="portal_verify"),
    path("portal/login/", views.login_view, name="portal_login"),
    path("portal/logout/", views.logout_view, name="portal_logout"),
    path("portal/", views.portal_dashboard, name="portal_dashboard"),
    path("portal/apply/<int:advt_id>/", views.apply, name="portal_apply"),
    path("portal/applications/", views.my_applications, name="portal_my_applications"),
    path(
        "portal/applications/<str:application_id>/",
        views.application_detail,
        name="portal_application_detail",
    ),
    path(
        "portal/applications/<str:application_id>/withdraw/",
        views.withdraw_application,
        name="portal_application_withdraw",
    ),
    path(
        "portal/applications/<str:application_id>/slip/",
        views.application_slip,
        name="portal_application_slip",
    ),
    path("portal/consents/", views.consent_list, name="portal_consents"),
    path("portal/profile/", views.profile_view, name="portal_profile"),
    path("portal/consents/<int:consent_id>/revoke/", views.consent_revoke, name="portal_consent_revoke"),
]
