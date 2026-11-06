"""AST-based import guard for the cross-tenant sweep accessor.

Ensures iter_stale_sites_for_sweep is ONLY imported by:
- its home module (apps/sites/reverification.py)
- the sweep command (apps/sites/management/commands/sweep_stale_verifications.py)
- test modules under backend/tests/
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

BANNED_SYMBOL = "iter_stale_sites_for_sweep"

# Relative paths normalized with forward slashes
PERMITTED_MODULES = {
    "apps/sites/reverification.py",
    "apps/sites/management/commands/sweep_stale_verifications.py",
}


def find_accessor_imports(source: str, file_path: str = "<unknown>") -> list[str]:
    """Parse python source and return violation messages if BANNED_SYMBOL is imported."""
    tree = ast.parse(source, filename=file_path)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == BANNED_SYMBOL:
                    violations.append(
                        f"Line {node.lineno}: 'from {node.module} import {alias.name}'"
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == BANNED_SYMBOL or alias.name.endswith(f".{BANNED_SYMBOL}"):
                    violations.append(f"Line {node.lineno}: 'import {alias.name}'")

    return violations


def test_guard_self_test_detects_unauthorized_imports():
    """Verify that the AST guard flags unauthorized imports."""
    bad_code_from = "from apps.sites.reverification import iter_stale_sites_for_sweep"
    violations = find_accessor_imports(bad_code_from, "apps/sites/views.py")
    assert len(violations) == 1
    assert "Line 1" in violations[0]
    assert "iter_stale_sites_for_sweep" in violations[0]

    bad_code_import = "import apps.sites.reverification.iter_stale_sites_for_sweep"
    violations_import = find_accessor_imports(bad_code_import, "apps/accounts/views.py")
    assert len(violations_import) == 1


def test_guard_self_test_permits_benign_code():
    """Verify that benign code does not trigger false positives."""
    clean_code = "from apps.sites.reverification import reverify_site"
    assert find_accessor_imports(clean_code, "apps/sites/views.py") == []


def test_no_forbidden_accessor_imports_across_codebase():
    """Walk backend source files and assert iter_stale_sites_for_sweep is strictly scoped."""
    violations: list[str] = []

    for py_file in BACKEND_DIR.rglob("*.py"):
        if ".venv" in py_file.parts:
            continue

        rel_path = py_file.relative_to(BACKEND_DIR).as_posix()

        # Permitted modules
        if rel_path in PERMITTED_MODULES or rel_path.startswith("tests/"):
            continue

        source = py_file.read_text(encoding="utf-8")
        file_violations = find_accessor_imports(source, rel_path)
        for v in file_violations:
            violations.append(f"{rel_path}: {v}")

    assert not violations, "Forbidden cross-tenant sweep accessor imports found:\n" + "\n".join(
        violations
    )
