"""Background task isolation test harness.

Provides the verification registry and walk runner to ensure all registered
tenant tasks declare sample arguments for isolation testing.
"""

from __future__ import annotations

from typing import Any

from apps.core.tasks import TASK_REGISTRY

# Map from task name -> sample JSON-primitive arguments list
TASK_ISOLATION_CASES: dict[str, list[Any]] = {}


def check_task_isolation_registry() -> None:
    """Walk TASK_REGISTRY and assert every tenant task has an entry in TASK_ISOLATION_CASES."""
    missing: list[str] = []
    for meta in TASK_REGISTRY:
        if meta.kind == "tenant" and meta.name not in TASK_ISOLATION_CASES:
            missing.append(meta.name)

    if missing:
        raise AssertionError(
            f"Tenant tasks missing isolation test cases in TASK_ISOLATION_CASES: {missing}"
        )
