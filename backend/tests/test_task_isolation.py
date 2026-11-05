"""Tests for background task tenant isolation and isolation harness.

Verifies that tenant tasks execute with proper organization context,
never leak active organization state across sequential runs, and enforce
tenant scoping when accessing model rows via TenantManager.
"""

from __future__ import annotations

import pytest
from django.test import TestCase

from apps.core.tasks import TASK_REGISTRY, task
from apps.core.tenancy import get_current_organization
from apps.sites.models import Site
from tests.task_harness import TASK_ISOLATION_CASES, check_task_isolation_registry

pytestmark = pytest.mark.django_db


# Module-level probe functions for dynamic test registration
def sample_probe(value: int) -> None:
    pass


def unhandled_probe(value: int) -> None:
    pass


_observed_orgs: list[str | None] = []


def probe_recorder() -> None:
    curr = get_current_organization()
    _observed_orgs.append(str(curr.pk) if curr else None)


_observed_exceptions: list[Exception] = []


def probe_lookup(site_id: str) -> None:
    try:
        Site.objects.get(pk=site_id)
    except Site.DoesNotExist as exc:
        _observed_exceptions.append(exc)


@pytest.fixture(autouse=True)
def clean_task_registry_and_cases():
    initial_registry = list(TASK_REGISTRY)
    initial_cases = dict(TASK_ISOLATION_CASES)
    _observed_orgs.clear()
    _observed_exceptions.clear()
    try:
        yield
    finally:
        TASK_REGISTRY[:] = initial_registry
        TASK_ISOLATION_CASES.clear()
        TASK_ISOLATION_CASES.update(initial_cases)
        _observed_orgs.clear()
        _observed_exceptions.clear()


def test_harness_walk_passes_when_all_tenant_tasks_have_cases():
    """Verify that check_task_isolation_registry passes when tenant tasks have registered cases."""
    task(tenant=True)(sample_probe)
    TASK_ISOLATION_CASES[sample_probe.__name__] = [123]

    check_task_isolation_registry()


def test_harness_walk_fails_when_tenant_task_lacks_isolation_case():
    """Negative test: verify that a tenant task missing from TASK_ISOLATION_CASES fails loudly."""
    task(tenant=True)(unhandled_probe)

    with pytest.raises(AssertionError) as exc_info:
        check_task_isolation_registry()

    assert unhandled_probe.__name__ in str(exc_info.value)


def test_sequence_execution_does_not_leak_context(org_a, org_b):
    """Running two tenant tasks for different orgs sequentially leaves no leaked context."""
    wrapped = task(tenant=True)(probe_recorder)
    TASK_ISOLATION_CASES[probe_recorder.__name__] = []

    with TestCase.captureOnCommitCallbacks(execute=True):
        wrapped.enqueue(organization=org_a)

    assert get_current_organization() is None

    with TestCase.captureOnCommitCallbacks(execute=True):
        wrapped.enqueue(organization=org_b)

    assert get_current_organization() is None
    assert _observed_orgs == [str(org_a.pk), str(org_b.pk)]
    assert get_current_organization() is None


def test_task_body_loading_foreign_org_row_raises_does_not_exist(org_a, org_b, site_a):
    """Inside a tenant task scoped to org_b, loading org_a's site raises DoesNotExist."""
    wrapped = task(tenant=True)(probe_lookup)
    TASK_ISOLATION_CASES[probe_lookup.__name__] = [str(site_a.pk)]

    with TestCase.captureOnCommitCallbacks(execute=True):
        wrapped.enqueue(str(site_a.pk), organization=org_b)

    assert len(_observed_exceptions) == 1
    assert isinstance(_observed_exceptions[0], Site.DoesNotExist)
    assert get_current_organization() is None
