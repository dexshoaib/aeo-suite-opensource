"""Tenant-isolation primitives (ADR-0004) - the product-wide tenancy base.

One manager, one viewset, one request-less scoping helper (SPEC-0.2):

- TenantQuerySet / TenantManager: every tenant-scoped model declares an
  ``organization`` ForeignKey and uses TenantManager. The manager filters
  by the *active organization* (contextvar below) whenever one is active.
- TenantViewSet: the ONLY allowed base for tenant-scoped viewsets. It
  resolves the organization per request through the membership-checked
  resolver (ADR-0004 rule 3 - the header is a selector, never a
  credential), activates it, serves from a sticky-filtered queryset, and
  deactivates the context on response finalization. Missing/foreign/
  non-member orgs resolve to 404, never 403 (a 403 would confirm the
  organization exists).
- scope_to_organization(): explicit activation for request-less contexts
  (management commands, worker jobs, eager admin paths). For lazy
  querysets (e.g. admin get_queryset) prefer the sticky
  ``queryset.for_organization(org)`` instead.

Background tasks (SPEC-0.2 Deferrals #4): background-task coverage joins
the structural leak-test harness when the job-queue chunk lands;
scope_to_organization() is the designated hook for worker contexts until
then - job code must run inside it (or re-activate a stored organization
id) so base-manager scoping holds off the request path too.

Concrete viewsets subclassing TenantViewSet auto-register into
TENANT_VIEWSET_REGISTRY; the Task 9 leak test walks that registry, so a
tenant viewset that skips the base fails the harness instead of passing
silently. Intermediary abstract bases also land in the registry; the
harness filters them by ``queryset is None``.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from django.db import models
from rest_framework import viewsets

_current_organization: ContextVar = ContextVar("aeo_current_organization", default=None)

TENANT_VIEWSET_REGISTRY: list[type["TenantViewSet"]] = []


def get_current_organization():
    """Return the active organization for this context, or None."""
    return _current_organization.get()


def activate_organization(organization):
    """Activate ``organization`` for this context; returns a reset token."""
    return _current_organization.set(organization)


def deactivate_organization(token) -> None:
    """Deactivate the organization bound to ``token`` (always, even on error)."""
    _current_organization.reset(token)


@contextmanager
def scope_to_organization(organization):
    """
    Activate ``organization`` for the wrapped block (request-less contexts:
    management commands, worker jobs, eager admin paths).

    Every TenantManager queryset inside the block is scoped automatically.
    For lazy querysets use the sticky ``Model.objects.for_organization(org)``
    instead - the contextvar is local to this block, so a queryset built
    here but evaluated later is NOT scoped by it.
    """
    token = _current_organization.set(organization)
    try:
        yield
    finally:
        _current_organization.reset(token)


def resolve_organization(request):
    """
    Membership-checked org resolution (ADR-0004 rule 3, chunk 0.2 AC).

    Implemented by apps.accounts.org_context.resolve_organization (Task 5):
    org selector header -> server-side membership check -> Organization, or
    404 semantics (never 403) for a missing/foreign/non-member selector.
    Late-bound import keeps apps.core free of app-level dependencies.
    """
    from apps.accounts.org_context import resolve_organization as accounts_resolve

    return accounts_resolve(request)


class TenantQuerySet(models.QuerySet):
    """QuerySet for tenant rows (models with an ``organization`` ForeignKey)."""

    def for_organization(self, organization):
        """Sticky org filter - survives lazy evaluation (admin get_queryset)."""
        return self.filter(organization=organization)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """
    Base manager for every tenant-scoped model (ADR-0004 decision 1).

    Filters by the active organization whenever one is active (request path
    via TenantViewSet, request-less path via scope_to_organization). With
    no active organization the queryset is unscoped - that state is for
    system contexts only (migrations, fixtures, shell); both real paths
    are guarded by the structural leak test (Task 9).
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        organization = _current_organization.get()
        if organization is not None:
            return queryset.for_organization(organization)
        return queryset


class TenantViewSet(viewsets.ModelViewSet):
    """
    The ONLY base for tenant-scoped viewsets (ADR-0004 decision 1).

    Per request: authenticate/permit (DRF initial) -> resolve the org via
    the membership-checked resolver (404 on failure) -> activate the org
    contextvar -> serve from the sticky-filtered queryset -> deactivate in
    finalize_response (runs on both success and handled-error paths; only
    a pre-initial dispatch failure can skip it, which no handler reaches).

    Subclasses auto-register into TENANT_VIEWSET_REGISTRY for the Task 9
    structural leak test. No tenant viewset may bypass this base.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        TENANT_VIEWSET_REGISTRY.append(cls)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.organization = resolve_organization(request)
        self._organization_token = activate_organization(self.organization)

    def get_queryset(self):
        return super().get_queryset().for_organization(self.organization)

    def finalize_response(self, request, response, *args, **kwargs):
        try:
            return super().finalize_response(request, response, *args, **kwargs)
        finally:
            token = getattr(self, "_organization_token", None)
            if token is not None:
                deactivate_organization(token)
                self._organization_token = None
