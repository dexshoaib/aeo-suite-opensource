"""Tenant-scoped background task facade.

This module provides the single seam over the background task framework.
Tasks declare their scoping upfront (tenant or system). Tenant tasks are
guaranteed to execute with the active organization set in the execution
context, and their active organization is reset in a finally block.
Direct imports of the underlying task framework are forbidden across the
rest of the application.
"""

from __future__ import annotations

import functools
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

from django.db import transaction
from django.tasks.base import Task

from apps.core.tenancy import activate_organization, deactivate_organization

logger = logging.getLogger(__name__)

TASK_ARGS_MAX_BYTES: int = 10 * 1024  # 10 KB cap

SECRET_KEY_PATTERN = re.compile(r"(?i)(token|secret|password|api_?key|authorization)")


class TaskEnqueueError(ValueError):
    """Raised when task enqueue arguments or context violate contract rules."""


@dataclass(frozen=True)
class TaskMeta:
    """Metadata for registered tasks."""

    name: str
    kind: str  # "tenant" or "system"
    func: Callable[..., Any]
    backend: str
    queue_name: str
    wrapper: Any


TASK_REGISTRY: list[TaskMeta] = []


def _validate_arg_value(val: Any, path: str) -> None:
    if val is None:
        return
    if isinstance(val, bool):
        return
    if isinstance(val, (int, float, str)):
        return
    if isinstance(val, list):
        for idx, item in enumerate(val):
            _validate_arg_value(item, f"{path}[{idx}]")
        return
    if isinstance(val, dict):
        for k, v in val.items():
            if not isinstance(k, str):
                raise TaskEnqueueError(f"{path}: dict key must be str, got {type(k).__name__}")
            if SECRET_KEY_PATTERN.search(k):
                raise TaskEnqueueError(f"{path}.{k}: secret-like key forbidden")
            _validate_arg_value(v, f"{path}.{k}")
        return

    # Check for forbidden non-primitive types with rule-naming errors
    from django.db.models import Model

    if isinstance(val, Model):
        raise TaskEnqueueError(f"{path}: model instance forbidden")
    if isinstance(val, tuple):
        raise TaskEnqueueError(f"{path}: tuple forbidden, use list")
    if isinstance(val, set):
        raise TaskEnqueueError(f"{path}: set forbidden")
    from datetime import date, datetime

    if isinstance(val, (datetime, date)):
        raise TaskEnqueueError(f"{path}: datetime forbidden")
    from decimal import Decimal

    if isinstance(val, Decimal):
        raise TaskEnqueueError(f"{path}: decimal forbidden")

    raise TaskEnqueueError(f"{path}: {type(val).__name__} forbidden")


def _validate_args(args: tuple[Any, ...]) -> None:
    for idx, arg in enumerate(args):
        _validate_arg_value(arg, f"args[{idx}]")

    try:
        encoded = json.dumps(args).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TaskEnqueueError(f"Arguments are not JSON serializable: {exc}") from exc

    if len(encoded) > TASK_ARGS_MAX_BYTES:
        raise TaskEnqueueError(
            f"Arguments exceed {TASK_ARGS_MAX_BYTES} bytes cap ({len(encoded)} bytes)"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskWrapper(Task):
    """Wrapper around an underlying task providing tenant isolation and commit gating."""

    kind: str
    orig_func: Callable[..., Any]

    def enqueue(self, *args: Any, organization: Any = None, **kwargs: Any) -> None:
        """Enqueue task execution only after the current transaction commits."""
        if kwargs:
            raise TaskEnqueueError(
                "Keyword arguments are not supported; pass positional arguments only"
            )

        _validate_args(args)

        if self.kind == "tenant":
            if organization is None:
                raise TaskEnqueueError("Tenant task requires an organization")
            if hasattr(organization, "pk"):
                org_pk = str(organization.pk)
            else:
                org_pk = str(organization)

            transaction.on_commit(lambda: super(TaskWrapper, self).enqueue(org_pk, *args))
        else:
            if organization is not None:
                raise TaskEnqueueError("System task does not accept an organization")

            transaction.on_commit(lambda: super(TaskWrapper, self).enqueue(*args))

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.orig_func(*args, **kwargs)


def task(
    *,
    tenant: bool | None = None,
    system: bool | None = None,
    backend: str = "default",
    queue_name: str = "default",
) -> Callable[[Callable[..., Any]], TaskWrapper]:
    """Decorator to declare a background task with explicit tenant or system scoping."""
    if tenant is None and system is None:
        kind = "tenant"
    elif tenant is True and (system is False or system is None):
        kind = "tenant"
    elif system is True and (tenant is False or tenant is None):
        kind = "system"
    else:
        raise ValueError("Must specify either tenant=True or system=True (not both)")

    def decorator(func: Callable[..., Any]) -> TaskWrapper:
        if kind == "tenant":

            @functools.wraps(func)
            def runner(org_pk: str, *args: Any) -> Any:
                from apps.accounts.models import Organization

                try:
                    org = Organization.objects.filter(pk=org_pk).first()
                except Exception:
                    org = None

                if org is None:
                    logger.warning(
                        "task=%s org=%s organization missing, skipping",
                        func.__name__,
                        org_pk,
                    )
                    return None

                token = activate_organization(org)
                try:
                    return func(*args)
                except Exception as exc:
                    logger.error(
                        "task=%s org=%s error=%r",
                        func.__name__,
                        org_pk,
                        exc,
                    )
                    raise
                finally:
                    deactivate_organization(token)

        else:

            @functools.wraps(func)
            def runner(*args: Any) -> Any:
                try:
                    return func(*args)
                except Exception as exc:
                    logger.error(
                        "task=%s error=%r",
                        func.__name__,
                        exc,
                    )
                    raise

        wrapper = TaskWrapper(
            func=runner,
            kind=kind,
            orig_func=func,
            backend=backend,
            queue_name=queue_name,
        )
        meta = TaskMeta(
            name=func.__name__,
            kind=kind,
            func=func,
            backend=backend,
            queue_name=queue_name,
            wrapper=wrapper,
        )
        TASK_REGISTRY.append(meta)
        return wrapper

    return decorator
