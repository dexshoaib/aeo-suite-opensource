"""Tests for background site re-verification task and CAS logic.

Verifies:
- Test 12 [M]: CAS race discards and logs
- Test 13 [M]: Cleared only when both attempts fail (flap confirmation)
- Test 14 [M]: First fails definitive, second succeeds -> not cleared
- Test 15 [M]: Transient leaves verified_at unchanged
- Test 16 [M]: Deleted site clean stop (site_missing)
- Test 17 [M]: Org gone clean stop
- Test 23 [P]: Foreign-org site id -> DoesNotExist
- Test 24 [P]: Log hygiene: no token/body/IP in any log record
- Seam mocked across all tests: zero network access
"""

from __future__ import annotations

import datetime
import logging
import uuid
from unittest import mock

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.core.tenancy import scope_to_organization
from apps.sites.models import Site
from apps.sites.reverification import (
    RESULT_FAILED_CONFIRMED,
    RESULT_FAILED_TRANSIENT,
    RESULT_RACE_DISCARDED,
    RESULT_REVERIFIED,
    RESULT_SITE_MISSING,
    reverify_site,
)
from apps.sites.verification import (
    CODE_NETWORK,
    CODE_NO_TOKEN,
    CODE_TIMEOUT,
    VerificationOutcome,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Test 12 [M]: CAS race discards and logs
# ---------------------------------------------------------------------------


def test_cas_race_discards_and_logs(org_a, workspace_a, caplog):
    """When a concurrent write updates verification_checked_at during evaluation,

    the CAS update matches 0 rows, discards the outcome, and logs race_discarded.
    """
    initial_checked = timezone.now() - datetime.timedelta(days=10)
    with scope_to_organization(org_a):
        site = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="cas-race.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=initial_checked,
            verification_checked_at=initial_checked,
            verification_token="test-token-123",
        )

    # Mock evaluate_site_verification so that during evaluation, another process updates the site
    def simulate_concurrent_update(target_site):
        with scope_to_organization(org_a):
            Site.objects.filter(pk=target_site.pk).update(
                verification_checked_at=timezone.now(),
            )
        return VerificationOutcome(success=True, error_code="", is_transient=False)

    caplog.set_level(logging.INFO, logger="aeo.sites.reverification")

    with mock.patch(
        "apps.sites.reverification.evaluate_site_verification",
        side_effect=simulate_concurrent_update,
    ):
        with TestCase.captureOnCommitCallbacks(execute=True):
            reverify_site.enqueue(str(site.id), organization=org_a)

    assert f"site_id={site.pk} org_id={org_a.pk} result={RESULT_RACE_DISCARDED}" in caplog.text


# ---------------------------------------------------------------------------
# Test 13 [M]: Flap confirmation — cleared only when BOTH attempts fail
# ---------------------------------------------------------------------------


def test_flap_confirmation_cleared_only_when_both_fail(org_a, workspace_a, caplog):
    """When both attempts fail definitively, verified_at is cleared and status is FAILED."""
    initial_verified = timezone.now() - datetime.timedelta(days=10)
    with scope_to_organization(org_a):
        site = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="flap-fail.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=initial_verified,
            verification_checked_at=initial_verified,
            verification_token="test-token-123",
        )

    fail_outcome = VerificationOutcome(success=False, error_code=CODE_NO_TOKEN, is_transient=False)
    caplog.set_level(logging.INFO, logger="aeo.sites.reverification")

    with mock.patch(
        "apps.sites.reverification.evaluate_site_verification",
        return_value=fail_outcome,
    ) as mock_eval:
        with TestCase.captureOnCommitCallbacks(execute=True):
            reverify_site.enqueue(str(site.id), organization=org_a)

        # Flap confirmation called evaluate twice
        assert mock_eval.call_count == 2

    site.refresh_from_db()
    assert site.verification_status == Site.VerificationStatus.FAILED
    assert site.verified_at is None
    assert site.verification_error == CODE_NO_TOKEN
    assert f"site_id={site.pk} org_id={org_a.pk} result={RESULT_FAILED_CONFIRMED}" in caplog.text


# ---------------------------------------------------------------------------
# Test 14 [M]: First fails definitive, second succeeds/transient -> NOT cleared
# ---------------------------------------------------------------------------


def test_first_fails_second_succeeds_not_cleared(org_a, workspace_a, caplog):
    """If attempt 1 fails definitively but attempt 2 succeeds, verified_at is NOT cleared."""
    initial_verified = timezone.now() - datetime.timedelta(days=10)
    with scope_to_organization(org_a):
        site = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="flap-recover.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=initial_verified,
            verification_checked_at=initial_verified,
            verification_token="test-token-123",
        )

    fail_outcome = VerificationOutcome(success=False, error_code=CODE_NO_TOKEN, is_transient=False)
    success_outcome = VerificationOutcome(success=True, error_code="", is_transient=False)
    caplog.set_level(logging.INFO, logger="aeo.sites.reverification")

    with mock.patch(
        "apps.sites.reverification.evaluate_site_verification",
        side_effect=[fail_outcome, success_outcome],
    ) as mock_eval:
        with TestCase.captureOnCommitCallbacks(execute=True):
            reverify_site.enqueue(str(site.id), organization=org_a)

        assert mock_eval.call_count == 2

    site.refresh_from_db()
    assert site.verification_status == Site.VerificationStatus.VERIFIED
    assert site.verified_at is not None
    assert site.verification_error == ""
    assert f"site_id={site.pk} org_id={org_a.pk} result={RESULT_REVERIFIED}" in caplog.text


def test_first_fails_second_transient_not_cleared(org_a, workspace_a, caplog):
    """If attempt 1 fails definitively but attempt 2 is transient, verified_at is NOT cleared."""
    initial_verified = timezone.now() - datetime.timedelta(days=10)
    with scope_to_organization(org_a):
        site = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="flap-transient.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=initial_verified,
            verification_checked_at=initial_verified,
            verification_token="test-token-123",
        )

    fail_outcome = VerificationOutcome(success=False, error_code=CODE_NO_TOKEN, is_transient=False)
    transient_outcome = VerificationOutcome(
        success=False, error_code=CODE_TIMEOUT, is_transient=True
    )
    caplog.set_level(logging.INFO, logger="aeo.sites.reverification")

    with mock.patch(
        "apps.sites.reverification.evaluate_site_verification",
        side_effect=[fail_outcome, transient_outcome],
    ) as mock_eval:
        with TestCase.captureOnCommitCallbacks(execute=True):
            reverify_site.enqueue(str(site.id), organization=org_a)

        assert mock_eval.call_count == 2

    site.refresh_from_db()
    assert site.verification_status == Site.VerificationStatus.VERIFIED
    assert site.verified_at == initial_verified
    assert site.verification_error == CODE_TIMEOUT
    assert f"site_id={site.pk} org_id={org_a.pk} result={RESULT_FAILED_TRANSIENT}" in caplog.text


# ---------------------------------------------------------------------------
# Test 15 [M]: Transient leaves verified_at unchanged
# ---------------------------------------------------------------------------


def test_transient_leaves_verified_at_unchanged(org_a, workspace_a, caplog):
    """A transient error on attempt 1 does not clear verified_at or trigger flap attempt 2."""
    initial_verified = timezone.now() - datetime.timedelta(days=10)
    with scope_to_organization(org_a):
        site = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="transient.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=initial_verified,
            verification_checked_at=initial_verified,
            verification_token="test-token-123",
        )

    transient_outcome = VerificationOutcome(
        success=False, error_code=CODE_NETWORK, is_transient=True
    )
    caplog.set_level(logging.INFO, logger="aeo.sites.reverification")

    with mock.patch(
        "apps.sites.reverification.evaluate_site_verification",
        return_value=transient_outcome,
    ) as mock_eval:
        with TestCase.captureOnCommitCallbacks(execute=True):
            reverify_site.enqueue(str(site.id), organization=org_a)

        # Single attempt: transient does not trigger attempt 2
        assert mock_eval.call_count == 1

    site.refresh_from_db()
    assert site.verification_status == Site.VerificationStatus.VERIFIED
    assert site.verified_at == initial_verified
    assert site.verification_error == CODE_NETWORK
    assert f"site_id={site.pk} org_id={org_a.pk} result={RESULT_FAILED_TRANSIENT}" in caplog.text


# ---------------------------------------------------------------------------
# Test 16 [M]: Deleted site clean stop
# ---------------------------------------------------------------------------


def test_deleted_site_clean_stop(org_a, caplog):
    """When a site does not exist globally, the task logs site_missing and stops cleanly."""
    deleted_site_id = str(uuid.uuid4())
    caplog.set_level(logging.WARNING, logger="aeo.sites.reverification")

    with TestCase.captureOnCommitCallbacks(execute=True):
        reverify_site.enqueue(deleted_site_id, organization=org_a)

    assert f"site_id={deleted_site_id} result={RESULT_SITE_MISSING}" in caplog.text


# ---------------------------------------------------------------------------
# Test 17 [M]: Org gone clean stop
# ---------------------------------------------------------------------------


def test_org_gone_clean_stop(workspace_a, caplog):
    """When the target organization is deleted, the facade catches it and skips execution."""
    from apps.accounts.models import Organization

    temp_org = Organization.objects.create(name="Ephemeral Org")
    temp_org_id = str(temp_org.pk)

    with scope_to_organization(temp_org):
        site = Site.objects.create(
            organization=temp_org,
            workspace=workspace_a,
            domain="temp-org-site.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
            verification_token="test-token-123",
        )

    # Delete organization before task executes
    temp_org.delete()

    with caplog.at_level(logging.WARNING):
        with TestCase.captureOnCommitCallbacks(execute=True):
            reverify_site.enqueue(str(site.id), organization=temp_org_id)

    # Caught by task facade clean skip
    assert "organization missing, skipping" in caplog.text


# ---------------------------------------------------------------------------
# Test 23 [P]: Foreign-org site ID -> DoesNotExist
# ---------------------------------------------------------------------------


def test_foreign_org_site_id_raises_does_not_exist(org_a, org_b, workspace_b, caplog):
    """A site belonging to Org B cannot be accessed when enqueued under Org A (tenancy scoping)."""
    with scope_to_organization(org_b):
        site_b = Site.objects.create(
            organization=org_b,
            workspace=workspace_b,
            domain="foreign-org-site.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
            verification_token="test-token-123",
        )

    # Direct task body call under org_a scope raises Site.DoesNotExist
    with scope_to_organization(org_a):
        with pytest.raises(Site.DoesNotExist):
            reverify_site(str(site_b.id))

    # And executing via enqueue under org_a fails the task and logs DoesNotExist
    with caplog.at_level(logging.ERROR):
        with TestCase.captureOnCommitCallbacks(execute=True):
            reverify_site.enqueue(str(site_b.id), organization=org_a)

    assert "DoesNotExist" in caplog.text


# ---------------------------------------------------------------------------
# Test 24 [P]: Log hygiene — no token, response body, or IPs in any log record
# ---------------------------------------------------------------------------


def test_log_hygiene_no_token_body_or_ip(org_a, workspace_a, caplog):
    """Verify logs contain only site ID, org ID, and result code — never token, body, or IP."""
    token = "secret-super-sensitive-token-9999"
    with scope_to_organization(org_a):
        site = Site.objects.create(
            organization=org_a,
            workspace=workspace_a,
            domain="log-hygiene.com",
            verification_status=Site.VerificationStatus.VERIFIED,
            verified_at=timezone.now() - datetime.timedelta(days=10),
            verification_checked_at=timezone.now() - datetime.timedelta(days=10),
            verification_token=token,
        )

    success_outcome = VerificationOutcome(success=True, error_code="", is_transient=False)

    caplog.set_level(logging.DEBUG)

    with mock.patch(
        "apps.sites.reverification.evaluate_site_verification",
        return_value=success_outcome,
    ):
        with TestCase.captureOnCommitCallbacks(execute=True):
            reverify_site.enqueue(str(site.id), organization=org_a)

    all_logs = " ".join(record.getMessage() for record in caplog.records)

    assert token not in all_logs
    assert "127.0.0.1" not in all_logs
    assert "192.168." not in all_logs
    assert "<html>" not in all_logs
    assert f"site_id={site.pk}" in all_logs
    assert f"org_id={org_a.pk}" in all_logs
    assert f"result={RESULT_REVERIFIED}" in all_logs
