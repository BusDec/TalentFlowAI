from django.urls import path

from . import views

urlpatterns = [
    path("profile-import/", views.import_csv, name="profile_import"),
]
