"""Site ownership re-verification service and task.

Provides:
- reverify_site: tenant-scoped background task that evaluates stale verified sites
  using the site verification runner, confirmed by flap checking before clearing,
  and persisted via compare-and-swap (CAS).
- iter_stale_sites_for_sweep: single sanctioned cross-tenant accessor for sweep commands,
  returning only (site_id, organization_id) tuples.
"""

from __future__ import annotations

import collections
import datetime
import logging
import uuid
from typing import Iterator

from django.db.models import F, Q
from django.utils import timezone

from apps.core.tasks import task
from apps.core.tenancy import scope_to_organization
from apps.sites.models import Site
from apps.sites.verification import (
    VerificationOutcome,
    evaluate_site_verification,
)

logger = logging.getLogger("aeo.sites.reverification")

RESULT_REVERIFIED = "reverified"
RESULT_FAILED_CONFIRMED = "failed_confirmed"
RESULT_FAILED_TRANSIENT = "failed_transient"
RESULT_RACE_DISCARDED = "race_discarded"
RESULT_SITE_MISSING = "site_missing"


def cas_persist_outcome(
    site_id: uuid.UUID,
    read_checked_at: datetime.datetime | None,
    outcome: VerificationOutcome,
    is_flap_confirmed_failure: bool,
) -> str:
    """Persist verification outcome using compare-and-swap on verification_checked_at.

    Returns the result code ('reverified', 'failed_confirmed', 'failed_transient',
    or 'race_discarded' if a concurrent write modified the record).
    """
    now = timezone.now()
    updates: dict[str, object] = {
        "verification_checked_at": now,
        "updated_at": now,
    }

    if outcome.success:
        updates["verification_status"] = Site.VerificationStatus.VERIFIED
        updates["verified_at"] = now
        updates["verification_error"] = ""
        result_code = RESULT_REVERIFIED
    elif outcome.is_transient or not is_flap_confirmed_failure:
        # Transient failure or unconfirmed failure: verified_at and status unchanged.
        updates["verification_error"] = outcome.error_code
        result_code = RESULT_FAILED_TRANSIENT
    else:
        # Both attempts definitively failed: clear verified_at.
        updates["verification_status"] = Site.VerificationStatus.FAILED
        updates["verified_at"] = None
        updates["verification_error"] = outcome.error_code
        result_code = RESULT_FAILED_CONFIRMED

    if read_checked_at is None:
        qs = Site.objects.filter(pk=site_id, verification_checked_at__isnull=True)
    else:
        qs = Site.objects.filter(pk=site_id, verification_checked_at=read_checked_at)

    rows_updated = qs.update(**updates)
    if rows_updated == 0:
        return RESULT_RACE_DISCARDED

    return result_code


@task(tenant=True)
def reverify_site(site_id: str) -> str:
    """Tenant-scoped task to re-verify a site with flap confirmation and CAS.

    Loads the site through the tenant-scoped manager. If a foreign-org ID is
    requested, DoesNotExist is raised. If the site was deleted, stops cleanly.
    """
    try:
        site_uuid = uuid.UUID(site_id)
    except (ValueError, TypeError):
        logger.warning("site_id=%s result=%s", site_id, RESULT_SITE_MISSING)
        return RESULT_SITE_MISSING

    try:
        site = Site.objects.get(pk=site_uuid)
    except Site.DoesNotExist:
        with scope_to_organization(None):
            exists_globally = Site.objects.filter(pk=site_uuid).exists()
        if exists_globally:
            # Site exists but belongs to a different organization ->
            # raise DoesNotExist per tenancy scoping.
            raise
        logger.warning("site_id=%s result=%s", site_uuid, RESULT_SITE_MISSING)
        return RESULT_SITE_MISSING

    read_checked_at = site.verification_checked_at

    # Attempt 1
    outcome1 = evaluate_site_verification(site)
    if outcome1.success:
        final_outcome = outcome1
        is_confirmed = False
    elif outcome1.is_transient:
        final_outcome = outcome1
        is_confirmed = False
    else:
        # Definitive failure on attempt 1. Flap confirmation: run attempt 2 inside the same task.
        outcome2 = evaluate_site_verification(site)
        if outcome2.success:
            final_outcome = outcome2
            is_confirmed = False
        elif outcome2.is_transient:
            # First failed definitive, second transient -> not cleared (transient semantics)
            final_outcome = outcome2
            is_confirmed = False
        else:
            # Both attempts definitively failed
            final_outcome = outcome2
            is_confirmed = True

    result = cas_persist_outcome(
        site_id=site.pk,
        read_checked_at=read_checked_at,
        outcome=final_outcome,
        is_flap_confirmed_failure=is_confirmed,
    )

    if result == RESULT_REVERIFIED:
        with scope_to_organization(None):
            duplicates = (
                Site.objects.filter(
                    domain=site.domain,
                    verification_status=Site.VerificationStatus.VERIFIED,
                )
                .exclude(pk=site.pk)
                .exists()
            )
        if duplicates:
            logger.warning(
                "domain %s is now verified by more than one organization",
                site.domain,
            )

    logger.info("site_id=%s org_id=%s result=%s", site.pk, site.organization_id, result)
    return result


def iter_stale_sites_for_sweep(
    cutoff: datetime.datetime,
    per_org_limit: int,
    total_limit: int,
) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    """Yield (site_id, organization_id) tuples for sites needing re-verification.

    Selection predicate:
    verified_at IS NOT NULL AND
    (verification_checked_at IS NULL OR verification_checked_at < cutoff)

    Ordered by verification_checked_at ASC NULLS FIRST, id ASC.
    Cross-tenant read scoped strictly to returning (site_id, organization_id) tuples.
    """
    with scope_to_organization(None):
        qs = (
            Site.objects.filter(verified_at__isnull=False)
            .filter(Q(verification_checked_at__isnull=True) | Q(verification_checked_at__lt=cutoff))
            .order_by(F("verification_checked_at").asc(nulls_first=True), "id")
            .values_list("id", "organization_id")
        )

        counts_by_org: dict[uuid.UUID, int] = collections.defaultdict(int)
        total_yielded = 0

        for site_id, org_id in qs.iterator():
            if total_yielded >= total_limit:
                break
            if counts_by_org[org_id] >= per_org_limit:
                continue
            counts_by_org[org_id] += 1
            total_yielded += 1
            yield site_id, org_id
