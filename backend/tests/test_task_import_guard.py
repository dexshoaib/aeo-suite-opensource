"""AST-based import guard for background task infrastructure.

Ensures that apps/core/tasks.py is the ONLY file in the backend that directly
imports from django.tasks or django_tasks packages. All other modules must
use the tenant-aware facade.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
ALLOWLISTED_FILE = (BACKEND_ROOT / "apps" / "core" / "tasks.py").resolve()


def check_source_for_banned_task_imports(source: str) -> list[str]:
    """Inspect Python source via AST and return a list of violation descriptions."""
    tree = ast.parse(source)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if (
                    name == "django.tasks"
                    or name.startswith("django.tasks.")
                    or name == "django_tasks"
                    or name.startswith("django_tasks.")
                    or name == "django_tasks_db"
                    or name.startswith("django_tasks_db.")
                ):
                    violations.append(f"Line {node.lineno}: import {name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if (
                mod == "django.tasks"
                or mod.startswith("django.tasks.")
                or mod == "django_tasks"
                or mod.startswith("django_tasks.")
                or mod == "django_tasks_db"
                or mod.startswith("django_tasks_db.")
            ):
                violations.append(f"Line {node.lineno}: from {mod} import ...")
            elif mod == "django":
                for alias in node.names:
                    if alias.name == "tasks":
                        violations.append(f"Line {node.lineno}: from django import tasks")

    return violations


def test_guard_self_test_detects_banned_import_forms():
    """Verify that each banned import pattern is accurately caught by AST check."""
    cases = [
        ("import django.tasks", "import django.tasks"),
        ("import django.tasks.backends", "import django.tasks.backends"),
        ("import django_tasks", "import django_tasks"),
        ("import django_tasks_db", "import django_tasks_db"),
        ("from django.tasks import task", "from django.tasks import ..."),
        (
            "from django.tasks.backends.immediate import ImmediateBackend",
            "from django.tasks.backends.immediate import ...",
        ),
        ("from django_tasks import task", "from django_tasks import ..."),
        (
            "from django_tasks_db.models import DBTaskResult",
            "from django_tasks_db.models import ...",
        ),
        ("from django import tasks", "from django import tasks"),
    ]
    for code, expected_substring in cases:
        violations = check_source_for_banned_task_imports(code)
        assert violations, f"Expected violation for code: {code}"
        assert any(expected_substring in v for v in violations), (
            f"Expected '{expected_substring}' in {violations}"
        )


def test_guard_self_test_permits_facade_and_string_references():
    """Verify that valid facade usage and settings-style string paths pass."""
    valid_cases = [
        "from apps.core.tasks import task",
        "import apps.core.tasks",
        "TASKS = {'default': {'BACKEND': 'django.tasks.backends.immediate.ImmediateBackend'}}",
        "TASKS = {'default': {'BACKEND': 'django_tasks_db.DatabaseBackend'}}",
        "x = 'django.tasks'",
    ]
    for code in valid_cases:
        violations = check_source_for_banned_task_imports(code)
        assert not violations, f"Unexpected violation for valid code: {code} -> {violations}"


def test_no_forbidden_task_imports_across_codebase():
    """Scan all Python files in backend repository.
    Only apps/core/tasks.py may import task libraries.
    """
    all_violations: dict[str, list[str]] = {}

    ignored_dirs = {".venv", "__pycache__", "build", "dist", ".git", ".pytest_cache"}

    for py_path in BACKEND_ROOT.rglob("*.py"):
        # Skip virtualenvs or build caches
        if any(part in ignored_dirs for part in py_path.parts):
            continue

        resolved = py_path.resolve()
        if resolved == ALLOWLISTED_FILE:
            continue

        try:
            source = py_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        violations = check_source_for_banned_task_imports(source)
        if violations:
            rel_path = str(py_path.relative_to(BACKEND_ROOT))
            all_violations[rel_path] = violations

    assert not all_violations, (
        f"Forbidden direct task imports found outside apps/core/tasks.py: {all_violations}"
    )
