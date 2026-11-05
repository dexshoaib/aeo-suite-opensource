"""Unit tests for tenant-scoped background task facade.

Verifies argument validation, serialization limits, secret-key filtering,
commit gating, context management, clean-stop handling on deleted orgs,
and error logging contracts.
"""

from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from typing import Any

import pytest
from django.test import TestCase

from apps.accounts.models import Organization
from apps.core.tasks import (
    TASK_ARGS_MAX_BYTES,
    TASK_REGISTRY,
    TaskEnqueueError,
    task,
)
from apps.core.tenancy import get_current_organization

pytestmark = pytest.mark.django_db

_facade_runs: list[Any] = []


def facade_dummy_task(*args: Any) -> None:
    _facade_runs.append(args)


def facade_raising_task(*args: Any) -> None:
    raise RuntimeError("simulated task failure")


def facade_org_check_task() -> None:
    _facade_runs.append(get_current_organization())


def facade_system_task(val: int) -> int:
    _facade_runs.append(val)
    return val + 1


@pytest.fixture(autouse=True)
def clean_registry():
    initial_registry = list(TASK_REGISTRY)
    _facade_runs.clear()
    try:
        yield
    finally:
        TASK_REGISTRY[:] = initial_registry
        _facade_runs.clear()


def test_tenant_task_requires_organization():
    """Enqueueing a tenant task without an organization raises TaskEnqueueError synchronously."""
    wrapped = task(tenant=True)(facade_dummy_task)

    with pytest.raises(TaskEnqueueError, match="Tenant task requires an organization"):
        wrapped.enqueue(1, organization=None)


def test_system_task_rejects_organization(org_a):
    """Enqueueing a system task with an organization raises TaskEnqueueError synchronously."""
    wrapped = task(system=True)(facade_system_task)

    with pytest.raises(TaskEnqueueError, match="System task does not accept an organization"):
        wrapped.enqueue(1, organization=org_a)


def test_json_primitive_whitelist_rejects_model_instances(org_a):
    """Model instances in task arguments are forbidden."""
    wrapped = task(tenant=True)(facade_dummy_task)

    with pytest.raises(TaskEnqueueError, match=r"args\[0\]: model instance forbidden"):
        wrapped.enqueue(org_a, organization=org_a)

    with pytest.raises(TaskEnqueueError, match=r"args\[1\]\.user: model instance forbidden"):
        wrapped.enqueue("ok", {"user": org_a}, organization=org_a)


def test_json_primitive_whitelist_rejects_tuples_sets_datetimes_decimals(org_a):
    """Tuples, sets, datetimes, and Decimals are forbidden in task arguments."""
    wrapped = task(tenant=True)(facade_dummy_task)

    with pytest.raises(TaskEnqueueError, match=r"args\[0\]: tuple forbidden, use list"):
        wrapped.enqueue((1, 2), organization=org_a)

    with pytest.raises(TaskEnqueueError, match=r"args\[0\]: set forbidden"):
        wrapped.enqueue({1, 2}, organization=org_a)

    with pytest.raises(TaskEnqueueError, match=r"args\[0\]: datetime forbidden"):
        wrapped.enqueue(datetime.datetime.now(datetime.timezone.utc), organization=org_a)

    with pytest.raises(TaskEnqueueError, match=r"args\[0\]: decimal forbidden"):
        wrapped.enqueue(Decimal("12.34"), organization=org_a)


def test_arguments_size_cap_exceeded(org_a):
    """Arguments whose serialized JSON exceeds TASK_ARGS_MAX_BYTES are rejected synchronously."""
    wrapped = task(tenant=True)(facade_dummy_task)
    oversized_str = "x" * (TASK_ARGS_MAX_BYTES + 100)

    with pytest.raises(TaskEnqueueError, match="Arguments exceed 10240 bytes cap"):
        wrapped.enqueue(oversized_str, organization=org_a)


def test_secret_like_dict_keys_rejected(org_a):
    """Dictionary keys matching sensitive token/password/secret patterns are rejected."""
    wrapped = task(tenant=True)(facade_dummy_task)

    with pytest.raises(TaskEnqueueError, match=r"secret-like key forbidden"):
        wrapped.enqueue({"password": "secret"}, organization=org_a)

    with pytest.raises(TaskEnqueueError, match=r"secret-like key forbidden"):
        wrapped.enqueue({"api_key": "key123"}, organization=org_a)

    with pytest.raises(
        TaskEnqueueError, match=r"args\[0\]\.nested\.auth_token: secret-like key forbidden"
    ):
        wrapped.enqueue({"nested": {"auth_token": "tok"}}, organization=org_a)


def test_enqueue_deferred_until_commit(org_a):
    """Task enqueue is deferred until the enclosing transaction commits."""
    wrapped = task(tenant=True)(facade_dummy_task)

    # When callbacks are captured but not executed, task body has not run
    with TestCase.captureOnCommitCallbacks(execute=False) as callbacks:
        wrapped.enqueue(42, organization=org_a)

    assert len(callbacks) == 1
    assert len(_facade_runs) == 0

    # When callbacks execute at commit time, task body runs
    with TestCase.captureOnCommitCallbacks(execute=True):
        wrapped.enqueue(42, organization=org_a)

    assert _facade_runs == [(42,)]


def test_active_org_set_during_task_execution(org_a):
    """Inside tenant task execution, get_current_organization matches the enqueued organization."""
    wrapped = task(tenant=True)(facade_org_check_task)

    with TestCase.captureOnCommitCallbacks(execute=True):
        wrapped.enqueue(organization=org_a)

    assert len(_facade_runs) == 1
    assert _facade_runs[0] == org_a
    assert get_current_organization() is None


def test_active_org_reset_after_task_raising_exception(org_a):
    """When a task body raises an exception, the active organization context is still reset."""
    wrapped = task(tenant=True)(facade_raising_task)

    with TestCase.captureOnCommitCallbacks(execute=True):
        wrapped.enqueue(organization=org_a)

    assert get_current_organization() is None


def test_org_deleted_before_execution_skipped_with_warning(org_a, caplog):
    """If the target organization is deleted before callback execution,
    the task is safely skipped with a log.
    """
    wrapped = task(tenant=True)(facade_dummy_task)
    org_pk = str(org_a.pk)

    with TestCase.captureOnCommitCallbacks(execute=False) as callbacks:
        wrapped.enqueue(99, organization=org_a)

    assert len(callbacks) == 1

    # Organization is deleted before the transaction callback executes
    Organization.objects.filter(pk=org_pk).delete()

    with caplog.at_level(logging.WARNING):
        callbacks[0]()

    assert len(_facade_runs) == 0
    assert any("organization missing, skipping" in rec.message for rec in caplog.records)
    assert any(f"org={org_pk}" in rec.message for rec in caplog.records)
    assert get_current_organization() is None


def test_failure_logs_name_org_and_error_repr(org_a, caplog):
    """Task failure logs task name, organization PK, and the error representation."""
    wrapped = task(tenant=True)(facade_raising_task)
    org_pk = str(org_a.pk)

    with caplog.at_level(logging.ERROR):
        with TestCase.captureOnCommitCallbacks(execute=True):
            wrapped.enqueue(organization=org_a)

    error_logs = [rec for rec in caplog.records if rec.levelno == logging.ERROR]
    assert len(error_logs) >= 1
    log_text = error_logs[0].message
    assert f"task={facade_raising_task.__name__}" in log_text
    assert f"org={org_pk}" in log_text
    assert "simulated task failure" in log_text


def test_system_task_executes_without_organization():
    """System tasks execute cleanly without any organization context requirement."""
    wrapped = task(system=True)(facade_system_task)

    with TestCase.captureOnCommitCallbacks(execute=True):
        wrapped.enqueue(5)

    assert _facade_runs == [5]
    assert get_current_organization() is None
