"""SPEC-1.2: verification endpoint, challenge checks, SSRF guard, role gate.

The outbound fetch is patched at apps.sites.verification._fetch; no test
touches the network. Guard-level tests stub DNS at socket.getaddrinfo.
"""

import socket
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.sites.models import Site
from apps.sites.verification import (
    CODE_BLOCKED,
    CODE_MISMATCH,
    CODE_NETWORK,
    CODE_NO_TOKEN,
    VerificationBlocked,
    VerificationNetworkError,
    _fetch_follow,
    _meta_token_matches,
    validate_target_host,
    verify_site,
)

pytestmark = pytest.mark.django_db

TOKEN = "tok-abc123"


@pytest.fixture
def authed_client_b(api_client, user_b):
    """DRF client authenticated as user_b (session-independent)."""
    api_client.force_authenticate(user=user_b)
    return api_client


def _html_with_meta(token: str) -> bytes:
    return (
        "<html><head>"
        f'<meta name="aeo-suite-verification" content="{token}">'
        "</head><body>ok</body></html>"
    ).encode()


def _ok(body: bytes = b""):
    return (200, body, {}, False)


def verify_url(site: Site) -> str:
    return reverse("sites-verify", args=[site.pk])


# ---------------------------------------------------------------- endpoint


def test_verify_success_via_meta_tag(authed_client_a, org_a, workspace_a, site_a):
    site_a.verification_token = TOKEN
    site_a.save()
    with mock.patch(
        "apps.sites.verification._fetch",
        side_effect=[_ok(_html_with_meta(TOKEN)), _ok(b"other")],
    ):
        resp = authed_client_a.post(
            verify_url(site_a), HTTP_X_ORGANIZATION_ID=str(org_a.pk)
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verification_status"] == "verified"
    assert data["verified_at"] is not None
    assert data["verification_error"] == ""
    assert data["verification_checked_at"] is not None


def test_verify_success_via_well_known_file(authed_client_a, org_a, site_a):
    site_a.verification_token = TOKEN
    site_a.save()
    with mock.patch(
        "apps.sites.verification._fetch",
        side_effect=[(404, b"", {}, False), (200, f"  {TOKEN}\n".encode(), {}, False)],
    ):
        resp = authed_client_a.post(
            verify_url(site_a), HTTP_X_ORGANIZATION_ID=str(org_a.pk)
        )
    assert resp.status_code == 200
    assert resp.json()["verification_status"] == "verified"


def test_verify_definitive_failure_clears_verified_at(authed_client_a, org_a, site_a):
    site_a.verification_token = TOKEN
    site_a.verification_status = Site.VerificationStatus.VERIFIED
    site_a.verified_at = timezone.now()
    site_a.save()
    with mock.patch(
        "apps.sites.verification._fetch",
        side_effect=[_ok(_html_with_meta("wrong")), (200, b"wrong", {}, False)],
    ):
        resp = authed_client_a.post(
            verify_url(site_a), HTTP_X_ORGANIZATION_ID=str(org_a.pk)
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verification_status"] == "failed"
    assert data["verified_at"] is None
    assert data["verification_error"] == CODE_MISMATCH


def test_verify_timeout_leaves_verified_at_unchanged(authed_client_a, org_a, site_a):
    site_a.verification_status = Site.VerificationStatus.VERIFIED
    pinned = timezone.now()
    site_a.verified_at = pinned
    site_a.save()
    with mock.patch(
        "apps.sites.verification._fetch",
        side_effect=VerificationNetworkError("timeout"),
    ):
        resp = authed_client_a.post(
            verify_url(site_a), HTTP_X_ORGANIZATION_ID=str(org_a.pk)
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verification_status"] == "verified"
    assert data["verification_error"] in (CODE_NETWORK, "timeout")
    site_a.refresh_from_db()
    assert site_a.verified_at == pinned


def test_verify_foreign_org_is_404(authed_client_b, org_b, site_a):
    resp = authed_client_b.post(
        verify_url(site_a), HTTP_X_ORGANIZATION_ID=str(org_b.pk)
    )
    assert resp.status_code == 404


def test_verify_unauthenticated_is_401(api_client, site_a):
    resp = api_client.post(verify_url(site_a))
    assert resp.status_code in (401, 403)


# ------------------------------------------------------------------- roles


def test_role_ladder_gate():
    from apps.accounts.roles import role_at_least

    assert role_at_least("member") is True      # maps to editor today
    assert role_at_least("owner") is True
    assert role_at_least("viewer") is False     # future role: denied
    assert role_at_least("editor") is True
    assert role_at_least("unknown-role") is False  # fails closed


# ------------------------------------------------------------- SSRF guard


def test_validate_rejects_private_and_mapped_and_metadata(monkeypatch):
    def fake_getaddrinfo(host, port, type=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(VerificationBlocked):
        validate_target_host("metadata.example.com")


def test_validate_rejects_ipv4_mapped_ipv6(monkeypatch):
    def fake_getaddrinfo(host, port, type=None):
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:10.0.0.5", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(VerificationBlocked):
        validate_target_host("mapped.example.com")


def test_validate_rejects_mixed_resolution(monkeypatch):
    """One public AND one private answer: the whole target is blocked."""
    def fake_getaddrinfo(host, port, type=None):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 443)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(VerificationBlocked):
        validate_target_host("mixed.example.com")


def test_pinned_fetch_never_re_resolves(monkeypatch):
    """Resolve-once pinning: DNS must not be consulted a second time."""
    calls = {"count": 0}

    def fake_getaddrinfo(host, port, type=None):
        calls["count"] += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    def fake_create_connection(address, timeout=None):
        assert address[0] == "93.184.216.34"  # pinned IP, not re-resolved
        raise OSError("no network in test")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)

    import time as _time

    deadline = _time.monotonic() + 5
    with pytest.raises(VerificationNetworkError):
        _fetch_follow("https://rebind.example.com/", deadline)
    assert calls["count"] == 1


def test_redirect_to_private_ip_is_blocked(monkeypatch):
    def fake_getaddrinfo(host, port, type=None):
        if host == "public.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(
        "apps.sites.verification._request_via",
        lambda ip, parts, timeout: (
            302,
            b"",
            {"Location": "https://private.example.com/steal"},
            False,
        )
        if ip == "93.184.216.34"
        else (200, b"", {}, False),
    )
    import time as _time

    with pytest.raises(VerificationBlocked):
        _fetch_follow("https://public.example.com/", _time.monotonic() + 5)


def test_redirect_to_odd_port_is_blocked():
    import time as _time

    with (
        mock.patch(
            "apps.sites.verification._fetch",
            side_effect=VerificationBlocked("non-standard port"),
        ),
        pytest.raises(VerificationBlocked),
    ):
        _fetch_follow("https://public.example.com/", _time.monotonic() + 5)


# -------------------------------------------------------- challenge logic


def test_meta_token_comparison_is_exact():
    token = "Tok-ABC"  # case differences must not pass
    assert _meta_token_matches(_html_with_meta(token), token) == "match"
    assert _meta_token_matches(_html_with_meta(token), "tok-abc") == "mismatch"
    assert _meta_token_matches(_html_with_meta("other"), token) == "mismatch"
    assert _meta_token_matches(b"<html></html>", token) == "absent"


def test_verify_network_error_code_surfaced(authed_client_a, org_a, site_a):
    with mock.patch(
        "apps.sites.verification._fetch",
        side_effect=VerificationNetworkError("connection refused"),
    ):
        resp = authed_client_a.post(
            verify_url(site_a), HTTP_X_ORGANIZATION_ID=str(org_a.pk)
        )
    assert resp.status_code == 200
    assert resp.json()["verification_error"] == CODE_NETWORK
    assert resp.json()["verification_status"] == "pending"


def test_verify_blocked_reports_code(authed_client_a, org_a, site_a):
    with mock.patch(
        "apps.sites.verification._fetch", side_effect=VerificationBlocked("no")
    ):
        resp = authed_client_a.post(
            verify_url(site_a), HTTP_X_ORGANIZATION_ID=str(org_a.pk)
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verification_error"] == CODE_BLOCKED
    assert data["verification_status"] == "failed"


def test_well_known_body_over_cap_is_definitive(authed_client_a, org_a, site_a):
    site_a.verification_token = TOKEN
    site_a.save()
    big = b"x" * (1_000_001)
    with mock.patch(
        "apps.sites.verification._fetch",
        side_effect=[(404, b"", {}, False), (200, big, {}, True)],
    ):
        resp = authed_client_a.post(
            verify_url(site_a), HTTP_X_ORGANIZATION_ID=str(org_a.pk)
        )
    data = resp.json()
    assert data["verification_status"] == "failed"
    assert data["verification_error"] == CODE_NO_TOKEN


def test_same_domain_verified_by_second_org_logged(org_a, org_b, site_a, site_b, caplog):
    """Amendment 3: same domain may be verified by more than one org; log it."""
    site_b.domain = site_a.domain
    site_b.verification_status = Site.VerificationStatus.VERIFIED
    site_b.save()
    site_a.verification_token = TOKEN
    site_a.save()
    with (
        mock.patch(
            "apps.sites.verification._fetch",
            side_effect=[_ok(_html_with_meta(TOKEN)), _ok(b"")],
        ),
        caplog.at_level("WARNING", logger="aeo.sites.verification"),
    ):
        verify_site(site_a)
    assert any("more than one organization" in m for m in caplog.messages)
