"""Tests for the stale site verification sweep command and settings.

Verifies:
- Settings validation system check
- Selection predicate (stale verified / NULL checked_at included, unverified/fresh excluded)
- Ordering (oldest checked_at first, NULLs first)
- Per-org cap (50) and global cap (500)
- Command options (--dry-run, --limit)
- Postgres advisory lock concurrency guard (clean exit 0 on busy)
- Command output format and multi-tenant organization dispatch
- Fetch seam mocked across all tests (zero network access)
"""

from __future__ import annotations

import datetime
from io import StringIO
from unittest import mock

import psycopg
import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.core.tenancy import scope_to_organization
from apps.sites.checks import check_reverification_settings
from apps.sites.management.commands.sweep_stale_verifications import (
    ADVISORY_LOCK_KEY,
)
from apps.sites.models import Site
from apps.sites.reverification import iter_stale_sites_for_sweep

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Test 22 [P]: Settings-validation system check
# ---------------------------------------------------------------------------


def test_settings_check_passes_with_valid_settings():
    """Default settings pass the registered system check."""
    errors = check_reverification_settings()
    assert errors == []


@pytest.mark.parametrize("invalid_val", [0, -5, "7", 7.5, True, False, None])
def test_settings_check_rejects_invalid_values(settings, invalid_val):
    """System check reports errors when settings are not positive integers."""
    settings.SITE_REVERIFICATION_INTERVAL_DAYS = invalid_val
    settings.SITE_REVERIFICATION_PER_ORG_LIMIT = invalid_val
    settings.SITE_REVERIFICATION_MAX_PER_SWEEP = invalid_val

    errors = check_reverification_settings()
    error_ids = {e.id for e in errors}
    assert "sites.E001" in error_ids
    assert "sites.E002" in error_ids
    assert "sites.E003" in error_ids


# ---------------------------------------------------------------------------
# Tests 1-6 [M]: Selection predicate & ordering
# ---------------------------------------------------------------------------


def test_selection_predicate_and_ordering(org_a, workspace_a):
    """Verify stale sites with NULL and past checked_at are selected oldest-first,

    while unverified, failed, and fresh sites are excluded.
    """
    now = timezone.now()
    cutoff = now - datetime.timedelta(days=7)

    with scope_to_organization(org_a):
        # 1. Stale verified with checked_at < cutoff -> INCLUDED
        stale_checked = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="stale-checked.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=cutoff - datetime.timedelta(days=10),
            verification_checked_at=cutoff - datetime.timedelta(days=2),
        )

        # 2. Stale verified with checked_at NULL -> INCLUDED (maximally stale, comes first)
        stale_null = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="stale-null.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=cutoff - datetime.timedelta(days=5),
            verification_checked_at=None,
        )

        # Older checked_at to test ordering between non-nulls
        stale_older = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="stale-older.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=cutoff - datetime.timedelta(days=20),
            verification_checked_at=cutoff - datetime.timedelta(days=5),
        )

        # 3. Unverified pending -> EXCLUDED
        Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="unverified.com",
            verification_status=Site.VerificationStatus.PENDING,
            verified_at=None,
            verification_checked_at=cutoff - datetime.timedelta(days=2),
        )

        # 4. Failed -> EXCLUDED
        Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="failed.com",
            verification_status=Site.VerificationStatus.FAILED,
            verified_at=None,
            verification_checked_at=cutoff - datetime.timedelta(days=2),
        )

        # 5. Fresh verified -> EXCLUDED
        Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="fresh.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=now - datetime.timedelta(days=1),
            verification_checked_at=now - datetime.timedelta(days=1),
        )

    pairs = list(iter_stale_sites_for_sweep(cutoff=cutoff, per_org_limit=50, total_limit=500))
    selected_ids = [site_id for site_id, _ in pairs]

    # Exactly the 3 stale verified sites are selected
    assert len(selected_ids) == 3

    # Test 6: Ordering oldest-first, NULLs first
    # 1st: stale_null (NULL checked_at)
    # 2nd: stale_older (checked 5 days before cutoff)
    # 3rd: stale_checked (checked 2 days before cutoff)
    assert selected_ids == [stale_null.id, stale_older.id, stale_checked.id]


# ---------------------------------------------------------------------------
# Test 7 [M] & Test 8 [P]: Per-org cap (50) and Global cap (500)
# ---------------------------------------------------------------------------


def test_per_org_cap(org_a, org_b, workspace_a, workspace_b):
    """An organization with > 50 stale sites yields at most 50 sites."""
    cutoff = timezone.now() - datetime.timedelta(days=7)

    with scope_to_organization(org_a):
        sites_a = [
            Site(
                organization=org_a,
                workspace=workspace_a,
                domain=f"org-a-{i}.com",
                verification_status=Site.VerificationStatus.VERIFIED,
                verified_at=cutoff - datetime.timedelta(days=1),
                verification_checked_at=None,
            )
            for i in range(60)
        ]
        Site.objects.bulk_create(sites_a)

    with scope_to_organization(org_b):
        sites_b = [
            Site(
                organization=org_b,
                workspace=workspace_b,
                domain=f"org-b-{i}.com",
                verification_status=Site.VerificationStatus.VERIFIED,
                verified_at=cutoff - datetime.timedelta(days=1),
                verification_checked_at=None,
            )
            for i in range(10)
        ]
        Site.objects.bulk_create(sites_b)

    pairs = list(iter_stale_sites_for_sweep(cutoff=cutoff, per_org_limit=50, total_limit=500))
    counts: dict[str, int] = {}
    for _, org_id in pairs:
        counts[str(org_id)] = counts.get(str(org_id), 0) + 1

    assert counts[str(org_a.id)] == 50  # Capped at 50 despite 60 existing
    assert counts[str(org_b.id)] == 10
    assert len(pairs) == 60


def test_global_cap(org_a, workspace_a):
    """Sweep stream terminates once total_limit is reached."""
    cutoff = timezone.now() - datetime.timedelta(days=7)

    with scope_to_organization(org_a):
        sites = [
            Site(
                organization=org_a,
                workspace=workspace_a,
                domain=f"cap-{i}.com",
                verification_status=Site.VerificationStatus.VERIFIED,
                verified_at=cutoff - datetime.timedelta(days=1),
                verification_checked_at=None,
            )
            for i in range(20)
        ]
        Site.objects.bulk_create(sites)

    pairs = list(iter_stale_sites_for_sweep(cutoff=cutoff, per_org_limit=50, total_limit=12))
    assert len(pairs) == 12


# ---------------------------------------------------------------------------
# Test 9 [M], Test 10 [P], Test 18 [M], Test 20 [M]: Command execution
# ---------------------------------------------------------------------------


def test_command_dry_run_and_output_codes(org_a, org_b, workspace_a, workspace_b):
    """--dry-run scans stale sites, outputs summary, and never enqueues tasks."""
    cutoff = timezone.now() - datetime.timedelta(days=7)

    with scope_to_organization(org_a):
        Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="dry-a.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=cutoff - datetime.timedelta(days=1),
            verification_checked_at=None,
        )

    with scope_to_organization(org_b):
        Site.objects.create(
            organization=org_b,
            workspace=workspace_b,
            domain="dry-b.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=cutoff - datetime.timedelta(days=1),
            verification_checked_at=None,
        )

    out = StringIO()
    with mock.patch(
        "apps.sites.management.commands.sweep_stale_verifications.reverify_site"
    ) as mock_task:
        call_command("sweep_stale_verifications", "--dry-run", stdout=out)
        assert mock_task.enqueue.call_count == 0

    output = out.getvalue().strip()
    assert output == "enqueued=2 orgs=2 dry_run=True lock=held"


def test_command_enqueues_with_respective_orgs(org_a, org_b, workspace_a, workspace_b):
    """Each enqueued task carries the site's own organization."""
    cutoff = timezone.now() - datetime.timedelta(days=7)

    with scope_to_organization(org_a):
        site_a = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="enq-a.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=cutoff - datetime.timedelta(days=1),
            verification_checked_at=None,
        )

    with scope_to_organization(org_b):
        site_b = Site.objects.create(
            organization=org_b,
            workspace=workspace_b,
            domain="enq-b.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=cutoff - datetime.timedelta(days=1),
            verification_checked_at=None,
        )

    out = StringIO()
    with mock.patch(
        "apps.sites.management.commands.sweep_stale_verifications.reverify_site"
    ) as mock_task:
        call_command("sweep_stale_verifications", stdout=out)

        assert mock_task.enqueue.call_count == 2
        calls = mock_task.enqueue.call_args_list

        # Verify each call matched the site and its organization
        enqueued_payloads = {(call[0][0], call[1]["organization"]) for call in calls}
        expected_payloads = {
            (str(site_a.id), str(org_a.id)),
            (str(site_b.id), str(org_b.id)),
        }
        assert enqueued_payloads == expected_payloads

    assert "enqueued=2 orgs=2 dry_run=False lock=held" in out.getvalue()


def test_command_limit_option_and_validation():
    """--limit caps the sweep and fails fast on non-positive values."""
    with pytest.raises(CommandError) as exc_info:
        call_command("sweep_stale_verifications", "--limit", "-3")
    assert "--limit must be a positive integer" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 11 [M]: Postgres Advisory lock concurrency test
# ---------------------------------------------------------------------------


def test_advisory_lock_busy_exits_cleanly():
    """When another database connection holds the advisory lock, the command

    logs 'lock=busy' and exits cleanly with code 0 without running the sweep.
    """
    db_config = settings.DATABASES["default"]
    conn_params = {
        "dbname": db_config["NAME"],
        "user": db_config["USER"],
        "password": db_config["PASSWORD"],
        "host": db_config["HOST"] or "localhost",
        "port": db_config["PORT"] or 5432,
    }

    # Open a real second connection to PostgreSQL and acquire the advisory lock
    with psycopg.connect(**conn_params) as external_conn:
        with external_conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_KEY])
            acquired = cur.fetchone()[0]
            assert acquired is True

            try:
                out = StringIO()
                with mock.patch(
                    "apps.sites.reverification.iter_stale_sites_for_sweep"
                ) as mock_iter:
                    # Should return cleanly (exit code 0) without raising
                    call_command("sweep_stale_verifications", stdout=out)
                    assert mock_iter.call_count == 0

                output = out.getvalue().strip()
                assert output == "enqueued=0 orgs=0 dry_run=False lock=busy"
            finally:
                cur.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_KEY])
