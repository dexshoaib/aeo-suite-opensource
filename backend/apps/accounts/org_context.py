"""Organization context resolution for the request path.

The ``X-Organization-ID`` header is a selector, never a credential: it
picks which of the authenticated user's organizations the request
operates on. Authority is always the server-side Membership row.

resolve_organization(request) is called by the tenant viewset base after
DRF authentication and returns:

- an Organization when the selector names an organization the user is a
  member of;
- None when no selector is sent (the caller decides what that means for
  its resources; tenant-scoped querysets then match nothing);
- Http404 for a malformed, unknown or non-member selector - every
  failure answers 404, never 403, because a 403 would confirm that an
  organization id exists.
"""

from uuid import UUID

from django.http import Http404

from apps.accounts.models import Organization

ORGANIZATION_HEADER = "X-Organization-ID"


def resolve_organization(request):
    """Return the Organization selected by the request header, or None.

    The header names an organization; the single membership-checked query
    below is the entire authority check. Unknown and non-member ids raise
    Http404 exactly like malformed ones, so responses never distinguish
    "does not exist" from "exists, not yours".
    """
    raw = (request.headers.get(ORGANIZATION_HEADER) or "").strip()
    if not raw:
        return None

    try:
        organization_id = UUID(raw)
    except ValueError as exc:
        raise Http404("Organization not found.") from exc

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        raise Http404("Organization not found.")

    try:
        return Organization.objects.get(pk=organization_id, memberships__user=user)
    except Organization.DoesNotExist as exc:
        raise Http404("Organization not found.") from exc
