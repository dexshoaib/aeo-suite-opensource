"""Integration test for DatabaseBackend worker execution on PostgreSQL.

Tests that a tenant task enqueued through the facade with backend="database"
persists to the database queue, is picked up and executed by manage.py db_worker
with --batch, sets the active organization during execution, resets context afterward,
and marks the task result as SUCCESSFUL.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.core.management import call_command
from django.db import transaction
from django.test import TransactionTestCase

from apps.accounts.models import Organization
from apps.core.tasks import TASK_REGISTRY, task
from apps.core.tenancy import get_current_organization

_db_worker_probe_runs: list[tuple[str | None, int]] = []


def raw_db_worker_probe(number: int) -> int:
    org = get_current_organization()
    _db_worker_probe_runs.append((str(org.pk) if org else None, number))
    return number * 2


class TaskDatabaseBackendIntegrationTest(TransactionTestCase):
    """Integration test suite executing real database queue tasks via db_worker."""

    def test_database_worker_processes_enqueued_tenant_task_to_completion(self):
        """Enqueue a tenant task into the database queue and process it via db_worker --batch."""
        _db_worker_probe_runs.clear()
        initial_registry = list(TASK_REGISTRY)

        db_task_result_model: Any = apps.get_model("django_tasks_database", "DBTaskResult")

        wrapped = task(tenant=True, backend="database")(raw_db_worker_probe)
        globals()["raw_db_worker_probe"] = wrapped

        try:
            with transaction.atomic():
                org = Organization.objects.create(name="DB Worker Integration Org")
                wrapped.enqueue(42, organization=org)

            # Confirm queue row was written to PostgreSQL
            matching_results = db_task_result_model.objects.filter(backend_name="database")
            assert matching_results.exists()
            initial_count = matching_results.count()
            assert initial_count >= 1

            # Drain queue using db_worker --batch
            call_command(
                "db_worker",
                "--batch",
                "--no-startup-delay",
                "--backend",
                "database",
            )

            # Verify probe executed inside active organization context
            assert len(_db_worker_probe_runs) == 1
            observed_org_pk, observed_number = _db_worker_probe_runs[0]
            assert observed_org_pk == str(org.pk)
            assert observed_number == 42

            # Verify context is completely clean after worker finishes
            assert get_current_organization() is None

            # Verify the result row status is SUCCESSFUL
            latest_result = (
                db_task_result_model.objects.filter(backend_name="database")
                .order_by("-enqueued_at")
                .first()
            )
            assert latest_result is not None
            assert latest_result.status == "SUCCESSFUL"
            assert latest_result.return_value == 84
        finally:
            TASK_REGISTRY[:] = initial_registry
            globals()["raw_db_worker_probe"] = raw_db_worker_probe
            _db_worker_probe_runs.clear()
