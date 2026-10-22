"""Shared fixtures: two organizations, their users, memberships, API client.

The org_a / org_b pair is the minimum setup for isolation testing:
user_a owns org_a, user_b owns org_b, and every foreign-organization
probe in the suite crosses exactly that boundary.
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Membership, Organization, User, Workspace


@pytest.fixture
def user_a(db):
    return User.objects.create_user(
        email="owner-a@example.com",
        password="test-password-a",
        full_name="Owner A",
    )


@pytest.fixture
def user_b(db):
    return User.objects.create_user(
        email="owner-b@example.com",
        password="test-password-b",
        full_name="Owner B",
    )


@pytest.fixture
def org_a(user_a):
    organization = Organization.objects.create(name="Org A")
    Membership.objects.create(
        organization=organization, user=user_a, role=Membership.Role.OWNER
    )
    return organization


@pytest.fixture
def org_b(user_b):
    organization = Organization.objects.create(name="Org B")
    Membership.objects.create(
        organization=organization, user=user_b, role=Membership.Role.OWNER
    )
    return organization


@pytest.fixture
def workspace_a(org_a):
    return Workspace.objects.create(organization=org_a, name="Workspace A1")


@pytest.fixture
def workspace_b(org_b):
    return Workspace.objects.create(organization=org_b, name="Workspace B1")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authed_client_a(api_client, user_a):
    """DRF client authenticated as user_a (session-independent)."""
    api_client.force_authenticate(user=user_a)
    return api_client
