"""Tests for crawler preflight token minting and contract verification."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.core.tenancy import scope_to_organization
from apps.sites.models import Site
from apps.sites.tokens import (
    derive_crawler_signing_key,
    mint_crawler_preflight_token,
)

pytestmark = pytest.mark.django_db


def test_mint_token_verified_site_success(org_a, workspace_a):
    """Verified site mints a valid token with expected claims."""
    with scope_to_organization(org_a):
        site = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="verified-target.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )

    fixed_now = 1731000000
    token = mint_crawler_preflight_token(site, now=fixed_now, key_id="v1")
    assert "." in token

    payload_b64, sig_b64 = token.split(".")
    # Pad base64 if needed
    padded_payload = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded_payload.encode("ascii")).decode("utf-8"))

    assert payload["v"] == 1
    assert payload["kid"] == "v1"
    assert payload["sub"] == str(site.id)
    assert payload["org"] == str(org_a.id)
    assert payload["dom"] == "verified-target.com"
    assert payload["iat"] == fixed_now
    assert payload["exp"] == fixed_now + 3600


def test_mint_token_unverified_site_raises_permission_denied(org_a, workspace_a):
    """Unverified site raises PermissionDenied."""
    with scope_to_organization(org_a):
        site = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="pending-site.com",
            verification_status=Site.VerificationStatus.PENDING,
            verified_at=None,
        )

    with pytest.raises(PermissionDenied, match="Site is not verified for crawling preflight"):
        mint_crawler_preflight_token(site)


def test_mint_token_verified_status_with_null_verified_at_raises(org_a, workspace_a):
    """Site marked verified but lacking verified_at timestamp raises PermissionDenied."""
    with scope_to_organization(org_a):
        site = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="inconsistent-site.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=None,
        )

    with pytest.raises(PermissionDenied):
        mint_crawler_preflight_token(site)


def test_mint_token_domain_normalization(org_a, workspace_a):
    """Domain with uppercase and trailing dot is normalized in token payload."""
    with scope_to_organization(org_a):
        site = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="UPPERCASE-DOMAIN.COM.",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )

    token = mint_crawler_preflight_token(site)
    payload_b64, _ = token.split(".")
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    assert payload["dom"] == "uppercase-domain.com"


def test_token_matches_shared_fixtures(org_a, workspace_a):
    """Token minting matches shared deterministic vectors file."""
    fixtures_path = (
        Path(__file__).resolve().parent.parent.parent
        / "shared_fixtures"
        / "crawler_token_vectors.json"
    )
    with open(fixtures_path, "r", encoding="utf-8") as f:
        vectors = json.load(f)

    secret_key = vectors["secret_key"]
    valid_data = vectors["valid"]
    payload = valid_data["payload"]
    expected_token = valid_data["token"]

    class MockSite:
        id = payload["sub"]
        organization_id = payload["org"]
        domain = payload["dom"]
        verification_status = Site.VerificationStatus.VERIFIED
        verified_at = timezone.now()

    token = mint_crawler_preflight_token(
        MockSite(),  # type: ignore[arg-type]
        now=payload["iat"],
        key_id=payload["kid"],
        secret_key=secret_key,
    )

    assert token == expected_token
    assert derive_crawler_signing_key(secret_key).hex() == vectors["derived_key_hex"]
