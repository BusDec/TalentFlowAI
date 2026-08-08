"""Shared pytest fixtures for TalentFlowAI.

django-tenants (schema-per-tenant) on PostgreSQL: each test creates a fresh
tenant schema (neepco.localhost) and activates it, mirroring TenantTestCase.
Shared-app models (accounts.User, tenants.Client) resolve through the public
schema because django-tenants appends "public" to the search_path.
"""

import pytest
from django.test import Client

from accounts.models import User, UserTenantMembership
from portal.models import CandidatePortalUser
from recruitment.models import Advertisement, Application, Candidate, Post
from tenants.models import Client as TenantClient
from tenants.models import Domain

TENANT_DOMAIN = "neepco.localhost"


def create_tenant(code="neepco"):
    tenant = TenantClient.objects.create(schema_name=code, name="NEEPCO", code=code)
    Domain.objects.create(domain=TENANT_DOMAIN, tenant=tenant, is_primary=True)
    return tenant


def make_staff_user(tenant, role, username):
    user = User.objects.create_user(
        username=username,
        password="pass",
        email=f"{username}@neepco.local",
        first_name=username.title(),
    )
    UserTenantMembership.objects.create(user=user, tenant=tenant, role=role, is_active=True)
    return user


@pytest.fixture
def tenant(db):
    """A Client + Domain in the public schema with its tenant schema activated."""
    t = create_tenant()
    t.activate()
    yield t
    t.deactivate()


@pytest.fixture
def staff_user(db, tenant):
    """accounts.User with an active hr_manager membership in the tenant."""
    return make_staff_user(tenant, "hr_manager", "staff1")


@pytest.fixture
def viewer_user(db, tenant):
    return make_staff_user(tenant, "viewer", "viewer1")


@pytest.fixture
def recruiter_user(db, tenant):
    return make_staff_user(tenant, "recruiter", "recruiter1")


@pytest.fixture
def org_admin_user(db, tenant):
    return make_staff_user(tenant, "org_admin", "orgadmin1")


@pytest.fixture
def super_admin_user(db, tenant):
    return make_staff_user(tenant, "super_admin", "super1")


@pytest.fixture
def candidate_portal_user(db, tenant):
    return CandidatePortalUser.objects.create(
        email="candidate@example.com",
        phone="9876543210",
        full_name="Aarav Sharma",
        otp_verified=True,
    )


@pytest.fixture
def advertisement(db, tenant):
    advt = Advertisement.objects.create(
        advt_number="TF/01/2026",
        title="Test Advertisement",
        published_date="2026-01-01",
        closing_date="2026-12-31",
    )
    Post.objects.create(
        advertisement=advt,
        name="Engineer",
        post_code="ENG-01",
        vacancies=1,
        qualification="B.Tech",
        category_breakup={"ur": 1},
    )
    Post.objects.create(
        advertisement=advt,
        name="Manager",
        post_code="MGR-01",
        vacancies=1,
        qualification="MBA",
    )
    return advt


@pytest.fixture
def application(db, tenant, advertisement):
    candidate = Candidate.objects.create(
        first_name="Aarav",
        last_name="Sharma",
        email="aarav@example.com",
        mobile="9876543210",
    )
    post = advertisement.posts.first()
    return Application.objects.create(
        post=post,
        candidate=candidate,
        application_id="TF20260001",
        status="received",
    )


@pytest.fixture
def api_client(db, tenant):
    """Django test client that always routes through the tenant hostname."""
    return Client(HTTP_HOST=TENANT_DOMAIN)
