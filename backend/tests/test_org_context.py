"""Selector-header probes: a non-member organization answers 404, never 403.

A 403 would confirm that an organization id exists; every failure mode
below (non-member, malformed, unknown) must be indistinguishable.
"""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

WORKSPACES = reverse("workspaces-list")


def test_non_member_header_is_404_not_403(authed_client_a, org_b):
    response = authed_client_a.get(WORKSPACES, HTTP_X_ORGANIZATION_ID=str(org_b.pk))
    assert response.status_code == 404


def test_malformed_header_is_404(authed_client_a):
    response = authed_client_a.get(WORKSPACES, HTTP_X_ORGANIZATION_ID="not-a-uuid")
    assert response.status_code == 404


def test_unknown_uuid_header_is_404(authed_client_a):
    response = authed_client_a.get(
        WORKSPACES, HTTP_X_ORGANIZATION_ID="00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


def test_missing_header_lists_empty_workspaces(authed_client_a, workspace_a):
    # No selector means no organization context: the list is empty, and
    # it never falls through to unscoped rows.
    response = authed_client_a.get(WORKSPACES)
    assert response.status_code == 200
    assert response.json() == []


def test_member_header_lists_only_that_org(authed_client_a, org_a, workspace_a):
    response = authed_client_a.get(WORKSPACES, HTTP_X_ORGANIZATION_ID=str(org_a.pk))
    assert response.status_code == 200
    assert [row["name"] for row in response.json()] == [workspace_a.name]
