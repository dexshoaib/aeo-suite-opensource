"""Site ownership verification service (SPEC-1.2).

Synchronous runner with one overall 10s deadline; the job-queue chunk
(1.3, ADR-0002) can enqueue verify_site() verbatim.

Security model (owner amendments):
- Resolve once, validate every resolved address, connect to the pinned
  IP with the original hostname for Host/SNI/certificate checking. No
  re-resolution, so DNS rebinding has no second window.
- HTTPS on port 443 only, no embedded credentials, every redirect hop
  re-validated, Accept-Encoding: identity, 1 MB body cap.
- Non-global addresses fail closed (is_global, after unrolling
  IPv4-mapped IPv6; 169.254.169.254 is link-local and rejected).
- Error codes only cross the API boundary; resolved IPs never do.
"""

import http.client
import ipaddress
import logging
import socket
import ssl
import time
import urllib.parse
from dataclasses import dataclass
from html.parser import HTMLParser

from django.utils import timezone

from apps.core.tenancy import scope_to_organization
from apps.sites.models import Site

logger = logging.getLogger("aeo.sites.verification")

OVERALL_DEADLINE_SECONDS = 10.0
MAX_REDIRECTS = 3
MAX_BODY_BYTES = 1_000_000
VERIFY_PORT = 443
USER_AGENT = "AEO-Suite-Verifier/0.1 (+https://github.com/dexshoaib/aeo-suite-opensource)"
META_NAME = "aeo-suite-verification"
WELL_KNOWN_PATH = "/.well-known/aeo-suite-verification.txt"

# Short machine codes exposed via the API (never raw exception text).
CODE_NO_TOKEN = "no_token"
CODE_MISMATCH = "mismatch"
CODE_TIMEOUT = "timeout"
CODE_NETWORK = "network_error"
CODE_BLOCKED = "blocked"
CODE_TOO_LARGE = "too_large"

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class VerificationBlocked(Exception):
    """Target failed the SSRF/shape guard: a definitive failure."""


class VerificationNetworkError(Exception):
    """Timeout/DNS/socket failure: transient, no verified_at change."""


class _MetaCollector(HTMLParser):
    """Collect meta tag (name, content) pairs; token comparison is exact."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metas: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "meta":
            return
        found = dict(attrs)
        name = found.get("name")
        content = found.get("content")
        if name is not None and content is not None:
            self.metas.append((name.lower(), content))


def validate_target_host(hostname: str) -> list[str]:
    """Resolve once and validate; return validated IPs in resolution order.

    Any non-global address among the results blocks the whole target:
    a mixed answer is exactly the rebinding case we must not race.
    """
    try:
        infos = socket.getaddrinfo(hostname, VERIFY_PORT, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise VerificationNetworkError(f"dns failure: {exc}") from exc

    ordered: list[str] = []
    for info in infos:
        raw = info[4][0]
        if raw not in ordered:
            ordered.append(raw)
    if not ordered:
        raise VerificationNetworkError("empty dns resolution")

    for raw in ordered:
        address = ipaddress.ip_address(raw)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if not address.is_global:
            raise VerificationBlocked(f"non-global address for {hostname}")
    return ordered


def _assert_https_shape(parts: urllib.parse.ParseResult) -> None:
    """HTTPS, standard port, no credentials. Redirects re-run this."""
    if parts.scheme != "https":
        raise VerificationBlocked("non-https target")
    if parts.port not in (None, VERIFY_PORT):
        raise VerificationBlocked("non-standard port")
    if parts.username or parts.password:
        raise VerificationBlocked("embedded credentials")


def _request_via(ip: str, parts: urllib.parse.ParseResult, timeout: float):
    """One HTTPS GET to the pinned IP; hostname carries SNI and cert check."""
    context = ssl.create_default_context()
    raw = socket.create_connection((ip, VERIFY_PORT), timeout=timeout)
    connection = http.client.HTTPSConnection(parts.hostname, timeout=timeout)
    connection.sock = context.wrap_socket(raw, server_hostname=parts.hostname)
    try:
        path = urllib.parse.urlunsplit(("", "", parts.path or "/", parts.query, ""))
        connection.request(
            "GET",
            path,
            headers={
                "Host": parts.hostname,
                "User-Agent": USER_AGENT,
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        body = response.read(MAX_BODY_BYTES + 1)
        too_large = len(body) > MAX_BODY_BYTES
        return response.status, body[:MAX_BODY_BYTES], dict(response.getheaders()), too_large
    finally:
        connection.close()


def _fetch(url: str, deadline: float):
    """Pinned fetch of one URL; returns (status, body, headers, too_large)."""
    parts = urllib.parse.urlsplit(url)
    _assert_https_shape(parts)
    validated = validate_target_host(parts.hostname)

    last_error: Exception | None = None
    for ip in validated:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise VerificationNetworkError("deadline exceeded")
        try:
            return _request_via(ip, parts, remaining)
        except VerificationBlocked:
            raise
        except (TimeoutError, socket.timeout) as exc:
            raise VerificationNetworkError("timeout") from exc
        except (OSError, ssl.SSLError) as exc:
            last_error = exc
            continue
    raise VerificationNetworkError(f"connect failed: {last_error}")


def _fetch_follow(url: str, deadline: float):
    """Fetch with https-only re-validated redirects (max 3 hops)."""
    for _ in range(MAX_REDIRECTS + 1):
        status, body, headers, too_large = _fetch(url, deadline)
        if status in _REDIRECT_STATUSES and not too_large:
            location = headers.get("Location", "")
            if not location:
                return status, body, too_large
            url = urllib.parse.urljoin(url, location)
            continue
        return status, body, too_large
    raise VerificationNetworkError("redirect limit exceeded")


def _meta_token_matches(html: bytes, token: str) -> str:
    """Return 'match' | 'mismatch' | 'absent' for the meta challenge."""
    collector = _MetaCollector()
    collector.feed(html.decode("utf-8", errors="replace"))
    contents = [content for name, content in collector.metas if name == META_NAME]
    if not contents:
        return "absent"
    return "match" if token in contents else "mismatch"


def _run_checks(domain: str, token: str, deadline: float) -> tuple[bool, str]:
    """Both challenges; any success wins. Returns (success, error_code).

    Failure priority when both attempts misbehave: definitive evidence
    beats transport trouble, so a page fetched clean without the token
    reports no_token even if the other method timed out.
    """
    outcomes: list[tuple[int, str]] = []  # (priority, code); lower wins
    homepage_url = f"https://{domain}/"
    well_known_url = f"https://{domain}{WELL_KNOWN_PATH}"

    try:
        status, body, too_large = _fetch_follow(homepage_url, deadline)
        if too_large:
            outcomes.append((3, CODE_TOO_LARGE))
        elif status != 200:
            outcomes.append((2, CODE_NO_TOKEN))
        else:
            verdict = _meta_token_matches(body, token)
            if verdict == "match":
                return True, ""
            outcomes.append((1, CODE_MISMATCH if verdict == "mismatch" else CODE_NO_TOKEN))
    except VerificationBlocked:
        outcomes.append((2, CODE_BLOCKED))
    except VerificationNetworkError as exc:
        code = CODE_TIMEOUT if "timeout" in str(exc) else CODE_NETWORK
        outcomes.append((4, code))

    try:
        status, body, too_large = _fetch_follow(well_known_url, deadline)
        if too_large:
            outcomes.append((3, CODE_TOO_LARGE))
        elif status != 200:
            outcomes.append((2, CODE_NO_TOKEN))
        elif body.decode("utf-8", errors="replace").strip() == token:
            return True, ""
        else:
            outcomes.append((1, CODE_MISMATCH))
    except VerificationBlocked:
        outcomes.append((2, CODE_BLOCKED))
    except VerificationNetworkError as exc:
        code = CODE_TIMEOUT if "timeout" in str(exc) else CODE_NETWORK
        outcomes.append((4, code))

    outcomes.sort(key=lambda item: item[0])
    return False, outcomes[0][1]


@dataclass(frozen=True)
class VerificationOutcome:
    success: bool
    error_code: str
    is_transient: bool


def evaluate_site_verification(site: Site) -> VerificationOutcome:
    """Evaluate domain ownership challenges without persisting changes."""
    deadline = time.monotonic() + OVERALL_DEADLINE_SECONDS
    success, code = _run_checks(site.domain, site.verification_token, deadline)
    is_transient = (not success) and (code in (CODE_TIMEOUT, CODE_NETWORK))
    return VerificationOutcome(
        success=success,
        error_code=code,
        is_transient=is_transient,
    )


def verify_site(site: Site) -> Site:
    """Run the challenges and write the outcome (amendment 3 semantics)."""
    outcome = evaluate_site_verification(site)

    site.verification_checked_at = timezone.now()
    if outcome.success:
        site.verification_status = Site.VerificationStatus.VERIFIED
        site.verified_at = timezone.now()
        site.verification_error = ""
    elif outcome.is_transient:
        # Transient: no evidence, so status and verified_at stay as they are.
        site.verification_error = outcome.error_code
    else:
        # Definitive failure (no_token/mismatch/blocked/too_large).
        site.verification_status = Site.VerificationStatus.FAILED
        site.verified_at = None
        site.verification_error = outcome.error_code
    site.save(
        update_fields=[
            "verification_status",
            "verified_at",
            "verification_checked_at",
            "verification_error",
            "updated_at",
        ]
    )

    if outcome.success:
        with scope_to_organization(None):
            duplicates = (
                Site.objects.filter(
                    domain=site.domain,
                    verification_status=Site.VerificationStatus.VERIFIED,
                )
                .exclude(pk=site.pk)
                .exists()
            )
        if duplicates:
            logger.warning(
                "domain %s is now verified by more than one organization",
                site.domain,
            )
    return site
