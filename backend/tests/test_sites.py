"""Tests for the sites API: CRUD, tenancy, workspace validation, domain normalization."""

import pytest
from django.urls import reverse

from apps.accounts.models import Workspace
from apps.sites.models import Site

pytestmark = pytest.mark.django_db


def test_list_sites_scoped_to_active_org(
    authed_client_a, org_a, org_b, workspace_a, site_a, site_b
):
    """Listing sites returns only sites belonging to the active organization."""
    url = reverse("sites-list")
    resp = authed_client_a.get(url, HTTP_X_ORGANIZATION_ID=str(org_a.pk))
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()]
    assert str(site_a.pk) in ids
    assert str(site_b.pk) not in ids


def test_missing_org_header_returns_empty_sites(authed_client_a, site_a):
    """Calling sites list with no selector returns empty list (no active org)."""
    url = reverse("sites-list")
    resp = authed_client_a.get(url)
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_site_normalizes_domain_and_binds_org(
    authed_client_a, org_a, workspace_a
):
    """Creating a site binds the active organization and normalizes the domain."""
    url = reverse("sites-list")
    payload = {
        "workspace": str(workspace_a.pk),
        "name": "Docs Portal",
        "domain": "HTTPS://Docs.Example.COM/guides/?ref=aeo",
    }
    resp = authed_client_a.post(
        url,
        data=payload,
        format="json",
        HTTP_X_ORGANIZATION_ID=str(org_a.pk),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Docs Portal"
    assert data["domain"] == "docs.example.com"
    assert data["organization"] == str(org_a.pk)
    assert data["workspace"] == str(workspace_a.pk)
    assert data["verification_status"] == "pending"
    assert "verification_token" in data

    # Verify persisted in database
    site = Site.objects.get(pk=data["id"])
    assert site.organization_id == org_a.pk
    assert site.domain == "docs.example.com"


def test_create_site_cross_org_workspace_rejected(
    authed_client_a, org_a, workspace_b
):
    """Submitting a foreign workspace ID returns 400 Bad Request."""
    url = reverse("sites-list")
    payload = {
        "workspace": str(workspace_b.pk),
        "name": "Intrusion Site",
        "domain": "intruder.example.com",
    }
    resp = authed_client_a.post(
        url,
        data=payload,
        format="json",
        HTTP_X_ORGANIZATION_ID=str(org_a.pk),
    )
    assert resp.status_code == 400
    assert "workspace" in resp.json()


def test_duplicate_domain_in_same_workspace_rejected(
    authed_client_a, org_a, workspace_a, site_a
):
    """Registering the same domain twice in the same workspace is rejected."""
    url = reverse("sites-list")
    payload = {
        "workspace": str(workspace_a.pk),
        "name": "Duplicate Site",
        "domain": site_a.domain,
    }
    resp = authed_client_a.post(
        url,
        data=payload,
        format="json",
        HTTP_X_ORGANIZATION_ID=str(org_a.pk),
    )
    assert resp.status_code == 400


def test_duplicate_domain_in_different_workspace_allowed(
    authed_client_a, org_a, workspace_a, site_a
):
    """The same domain can be registered in a different workspace."""
    workspace_a2 = Workspace.objects.create(organization=org_a, name="Workspace A2")
    url = reverse("sites-list")
    payload = {
        "workspace": str(workspace_a2.pk),
        "name": "Site in Workspace 2",
        "domain": site_a.domain,
    }
    resp = authed_client_a.post(
        url,
        data=payload,
        format="json",
        HTTP_X_ORGANIZATION_ID=str(org_a.pk),
    )
    assert resp.status_code == 201


def test_patch_site_cannot_reassign_workspace(
    authed_client_a, org_a, workspace_a, site_a
):
    """Attempting to alter workspace on PATCH is rejected (workspace immutability)."""
    workspace_a2 = Workspace.objects.create(organization=org_a, name="Workspace A2")
    url = reverse("sites-detail", args=[site_a.pk])
    resp = authed_client_a.patch(
        url,
        data={"workspace": str(workspace_a2.pk)},
        format="json",
        HTTP_X_ORGANIZATION_ID=str(org_a.pk),
    )
    assert resp.status_code == 400
    assert "workspace" in resp.json()


def test_filter_sites_by_workspace(authed_client_a, org_a, workspace_a, site_a):
    """Query parameter ?workspace=<uuid> filters sites to that workspace."""
    workspace_a2 = Workspace.objects.create(organization=org_a, name="Workspace A2")
    site_a2 = Site.objects.create(
        organization=org_a,
        workspace=workspace_a2,
        name="Site A2",
        domain="site-a2.example.com",
    )

    url = reverse("sites-list")
    resp = authed_client_a.get(
        f"{url}?workspace={workspace_a.pk}",
        HTTP_X_ORGANIZATION_ID=str(org_a.pk),
    )
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()]
    assert str(site_a.pk) in ids
    assert str(site_a2.pk) not in ids


def test_delete_own_site(authed_client_a, org_a, site_a):
    """Deleting a site returns 204 No Content."""
    url = reverse("sites-detail", args=[site_a.pk])
    resp = authed_client_a.delete(url, HTTP_X_ORGANIZATION_ID=str(org_a.pk))
    assert resp.status_code == 204
    assert not Site.objects.filter(pk=site_a.pk).exists()
