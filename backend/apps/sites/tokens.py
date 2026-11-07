"""Cryptographic token generator for crawler domain preflight gating."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.sites.models import Site

PREFLIGHT_SALT = b"aeo-crawler-preflight-token-v1"


def derive_crawler_signing_key(secret_key: str | None = None) -> bytes:
    """Derive a dedicated HMAC-SHA256 signing key from secret key and preflight salt."""
    raw_key = secret_key if secret_key is not None else settings.SECRET_KEY
    return hmac.new(raw_key.encode("utf-8"), PREFLIGHT_SALT, hashlib.sha256).digest()


def mint_crawler_preflight_token(
    site: Site,
    now: int | None = None,
    key_id: str | None = None,
    secret_key: str | None = None,
) -> str:
    """Mint a cryptographically signed HMAC-SHA256 token for crawler preflight.

    Preconditions:
    - Site must be VERIFIED and verified_at must be populated.
    - Otherwise raises PermissionDenied.
    """
    if site.verification_status != Site.VerificationStatus.VERIFIED or site.verified_at is None:
        raise PermissionDenied("Site is not verified for crawling preflight.")

    # Domain normalization: strip leading/trailing whitespace, lowercase, strip trailing dot
    normalized_domain = site.domain.strip().lower().rstrip(".")

    iat = int(now if now is not None else timezone.now().timestamp())
    exp = iat + 3600
    kid = key_id or getattr(settings, "CRAWLER_PREFLIGHT_KEY_ID", "v1")

    payload: dict[str, Any] = {
        "v": 1,
        "kid": kid,
        "sub": str(site.id),
        "org": str(site.organization_id),
        "dom": normalized_domain,
        "iat": iat,
        "exp": exp,
    }

    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("ascii").rstrip("=")

    derived_key = derive_crawler_signing_key(secret_key=secret_key)
    signature = hmac.new(derived_key, payload_b64.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")

    return f"{payload_b64}.{sig_b64}"
